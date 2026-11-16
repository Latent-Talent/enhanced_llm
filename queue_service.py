"""Enhancement queue bridge.

Only ComfyUI's existing prompt queue executes jobs. This module tracks a small
batch plan so successful partial LLM runs can enqueue an immutable full
workflow with their own generated text. The module never modifies ComfyUI core.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field

from aiohttp import web

LOGGER = logging.getLogger(__name__)
MAX_BATCH = 32
MAX_SNAPSHOT_BYTES = 8_000_000
LOCK = threading.RLock()
JOBS: dict[str, "Job"] = {}
BATCHES: dict[str, "Batch"] = {}
_routes_registered = False


@dataclass
class Job:
    id: str
    batch_id: str
    index: int
    state: str = "pending"
    full_prompt_id: str | None = None
    error: str | None = None


@dataclass
class Batch:
    id: str
    node_id: str
    run_each: bool
    template: dict
    workflow: dict | None
    client_id: str | None
    jobs: list[str] = field(default_factory=list)
    created: float = field(default_factory=time.time)
    cancelled: bool = False


def _server():
    from server import PromptServer
    return PromptServer.instance


async def _validate(prompt_id: str, prompt: dict, targets=None):
    from execution import validate_prompt
    valid = await validate_prompt(prompt_id, prompt, targets)
    if not valid[0]:
        raise ValueError(str(valid[1]))
    return valid[2]


def _number(server):
    # Called only on ComfyUI's single-threaded event loop.
    number = server.number
    server.number += 1
    return number


def _put(server, prompt_id, graph, targets, client_id, workflow):
    extra = {}
    if client_id:
        extra["client_id"] = client_id
    if workflow is not None:
        extra["extra_pnginfo"] = {"workflow": copy.deepcopy(workflow)}
    server.prompt_queue.put((
        _number(server), prompt_id, graph, extra, targets, {}
    ))


def _seeded_copy(template: dict, node_id: str, job_id: str, index: int):
    prompt = copy.deepcopy(template)
    inputs = prompt[node_id]["inputs"]
    inputs["ui_action"] = "enhance"
    inputs["enhancement_job_id"] = job_id
    inputs["enhancement_index"] = index
    # Deterministic, distinct sampling seeds for each enhancement request,
    # without modifying the user's native sampling settings.
    sampling = inputs.get("sampling_mode")
    if isinstance(sampling, dict) and sampling.get("sampling_mode") == "on":
        if isinstance(sampling.get("seed"), int):
            sampling["seed"] = (sampling["seed"] + index) % (1 << 64)
    return prompt


def _full_copy(batch: Batch, text: str, thinking: str):
    prompt = copy.deepcopy(batch.template)
    inputs = prompt[batch.node_id]["inputs"]
    inputs["ui_action"] = "pass"
    inputs["enhancement_job_id"] = ""
    inputs["enhanced_prompt"] = text
    inputs["enhanced_thinking"] = thinking
    # The pass-through path needs none of these model inputs. Removing their
    # links avoids loading the LLM during automatic full-workflow execution.
    for key in ("clip", "images", "videos", "audios", "system_prompt"):
        inputs.pop(key, None)
    return prompt


async def _complete(job_id: str, result: str, reasoning: str):
    with LOCK:
        job = JOBS.get(job_id)
        if job is None or job.state != "pending":
            return
        job.state = "enhanced"
        batch = BATCHES.get(job.batch_id)
    if batch is None:
        return
    if batch.cancelled or not batch.run_each:
        return
    server = _server()
    full_id = str(uuid.uuid4())
    try:
        full = _full_copy(batch, result, reasoning)
        outputs = await _validate(full_id, full)
        # Cancellation can arrive while validation is awaiting. Check again
        # immediately before the atomic queue insertion.
        with LOCK:
            if batch.cancelled:
                return
            _put(server, full_id, full, outputs, batch.client_id, batch.workflow)
            job.state = "full_queued"
            job.full_prompt_id = full_id
    except Exception as exc:
        LOGGER.exception("Unable to queue full workflow for enhancement %s", job_id)
        with LOCK:
            job.state = "full_error"
            job.error = str(exc)
        server.send_sync("enhanced_llm_status", {
            "job_id": job_id, "state": "full_error", "message": str(exc),
        }, batch.client_id)


def finish_job(job_id: str, text: str, thinking: str):
    """Called by the executing node, not by its browser UI."""
    with LOCK:
        if job_id not in JOBS or JOBS[job_id].state != "pending":
            return
    server = _server()
    future = asyncio.run_coroutine_threadsafe(
        _complete(job_id, text, thinking), server.loop
    )
    def report(f):
        try:
            f.result()
        except Exception:
            LOGGER.exception("Enhancement follow-up queue task failed")
    future.add_done_callback(report)


def cancel_batch_jobs(batch: Batch, server) -> None:
    """Cancel only jobs from this batch, never unrelated ComfyUI prompts.

    Completed full-workflow jobs already enqueued are left alone; the cancel
    button only stops remaining enhancements and their future follow-ups.
    """
    with LOCK:
        batch.cancelled = True
        pending = [job_id for job_id in batch.jobs
                   if JOBS[job_id].state == "pending"]
        for job_id in pending:
            JOBS[job_id].state = "cancelled"
    for job_id in pending:
        server.prompt_queue.delete_queue_item(lambda item, job_id=job_id: item[1] == job_id)
        server.prompt_queue.interrupt_if_running(job_id)


def _snapshot_status(batch: Batch):
    # A node may fail before it calls finish_job(). Reconcile those errors with
    # ComfyUI history so the UI never displays a permanently stuck counter.
    try:
        queue = _server().prompt_queue
        with LOCK:
            pending = [job_id for job_id in batch.jobs if JOBS[job_id].state == "pending"]
        for job_id in pending:
            history = queue.get_history(prompt_id=job_id)
            status = (history.get(job_id) or {}).get("status") or {}
            if status.get("status_str") == "error":
                with LOCK:
                    if JOBS[job_id].state == "pending":
                        JOBS[job_id].state = "error"
                        JOBS[job_id].error = str(status.get("messages") or "Enhancement execution failed.")
    except Exception:
        LOGGER.exception("Could not reconcile enhancement job history")
    with LOCK:
        return {
            "batch_id": batch.id,
            "run_each": batch.run_each,
            "cancelled": batch.cancelled,
            "jobs": [
                {"job_id": job_id, "state": JOBS[job_id].state,
                 "full_prompt_id": JOBS[job_id].full_prompt_id,
                 "error": JOBS[job_id].error}
                for job_id in batch.jobs
            ],
        }


def register_routes():
    global _routes_registered
    if _routes_registered:
        return
    server = _server()
    routes = server.routes

    @routes.post("/enhanced_llm/queue")
    async def queue_enhancements(request):
        try:
            body = await request.json()
            output = body["output"]
            node_id = str(body["node_id"])
            count = body["count"]
            run_each = body.get("queue_run_for_each", False)
            if type(count) is not int or not 1 <= count <= MAX_BATCH:
                raise ValueError("Enhancement count must be between 1 and 32.")
            if type(run_each) is not bool:
                raise ValueError("queue_run_for_each must be a boolean.")
            if not isinstance(output, dict) or node_id not in output:
                raise ValueError("Enhancement node missing from the graph.")
            from .nodes import NODE_ID
            if output[node_id].get("class_type") != NODE_ID:
                raise ValueError("Selected node is not an Enhanced LLM node.")
            inputs = output[node_id].get("inputs", {})
            if not isinstance(inputs.get("prompt"), str) or not inputs["prompt"].strip():
                raise ValueError("The original prompt is empty or connected to an unsupported input.")
            if not isinstance(inputs.get("enhancement_text"), str) or not inputs["enhancement_text"].strip():
                raise ValueError("The enhancement system prompt is empty.")
            if "clip" not in inputs:
                raise ValueError("Connect a CLIP model to the enhancement node.")
            import json
            if len(json.dumps(output)) > MAX_SNAPSHOT_BYTES:
                raise ValueError("Workflow is too large for one enhancement batch.")
            workflow = body.get("workflow")
            if workflow is not None and not isinstance(workflow, dict):
                raise ValueError("Invalid workflow metadata.")
            client_id = body.get("client_id")
            if client_id is not None and not isinstance(client_id, str):
                raise ValueError("Invalid client identifier.")
            template = copy.deepcopy(output)
            batch_id = str(uuid.uuid4())
            validated = []
            for index in range(count):
                job_id = str(uuid.uuid4())
                prompt = _seeded_copy(template, node_id, job_id, index)
                targets = await _validate(job_id, prompt, [node_id])
                validated.append((job_id, prompt, targets))
            batch = Batch(
                id=batch_id, node_id=node_id, run_each=run_each,
                template=template, workflow=workflow, client_id=client_id
            )
            with LOCK:
                BATCHES[batch_id] = batch
                for index, (job_id, _, _) in enumerate(validated):
                    batch.jobs.append(job_id)
                    JOBS[job_id] = Job(id=job_id, batch_id=batch_id, index=index)
            for job_id, prompt, targets in validated:
                _put(server, job_id, prompt, targets, client_id, workflow)
            return web.json_response(_snapshot_status(batch))
        except (ValueError, KeyError, TypeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except Exception:
            LOGGER.exception("Enhancement queue request failed")
            return web.json_response({"error": "Unable to queue enhancement batch."}, status=500)

    @routes.post("/enhanced_llm/batch/{batch_id}/cancel")
    async def cancel_batch_route(request):
        batch_id = request.match_info["batch_id"]
        with LOCK:
            batch = BATCHES.get(batch_id)
        if batch is None:
            return web.json_response({"error": "Batch not found."}, status=404)
        cancel_batch_jobs(batch, server)
        return web.json_response(_snapshot_status(batch))

    @routes.get("/enhanced_llm/batch/{batch_id}")
    async def batch_status(request):
        batch_id = request.match_info["batch_id"]
        with LOCK:
            batch = BATCHES.get(batch_id)
        if batch is None:
            return web.json_response({"error": "Batch not found."}, status=404)
        return web.json_response(_snapshot_status(batch))

    _routes_registered = True
