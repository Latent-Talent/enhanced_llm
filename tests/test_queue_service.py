"""Unit tests for immutable snapshots and linked full runs."""
import asyncio
import importlib.util
import pathlib
import sys
import types
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("test_queue_service_module", ROOT / "queue_service.py")
service = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = service
spec.loader.exec_module(service)


def template():
    return {
        "10": {
            "class_type": "LatentTalentEnhancedGenerateText",
            "inputs": {
                "prompt": "an ocean at sunrise",
                "enhancement_text": "Expand visually",
                "ui_action": "pass",
                "clip": ["1", 0],
                "images": {"image1": ["2", 0]},
                "sampling_mode": {"sampling_mode": "on", "seed": 120},
                "enhanced_prompt": "",
            },
        },
        "20": {"class_type": "SaveImage", "inputs": {"text": ["10", 0]}},
    }


def test_enhancement_jobs_are_immutable_and_seeded():
    raw = template()
    first = service._seeded_copy(raw, "10", "one", 0)
    second = service._seeded_copy(raw, "10", "two", 1)
    assert first["10"]["inputs"]["sampling_mode"]["seed"] == 120
    assert second["10"]["inputs"]["sampling_mode"]["seed"] == 121
    assert first["10"]["inputs"]["enhancement_job_id"] == "one"
    assert first["10"]["inputs"]["enhancement_index"] == 0
    assert second["10"]["inputs"]["enhancement_index"] == 1
    assert raw["10"]["inputs"]["ui_action"] == "pass"
    assert raw["10"]["inputs"]["sampling_mode"]["seed"] == 120


def test_full_pass_through_severs_model_links_without_mutating_template():
    batch = service.Batch(id="batch", node_id="10", run_each=True,
                          template=template(), workflow=None, client_id=None)
    full = service._full_copy(batch, "a luminous dawn", "analysis")
    inputs = full["10"]["inputs"]
    assert inputs["ui_action"] == "pass"
    assert inputs["enhanced_prompt"] == "a luminous dawn"
    assert inputs["enhanced_thinking"] == "analysis"
    assert "clip" not in inputs
    assert "images" not in inputs
    assert batch.template["10"]["inputs"]["clip"] == ["1", 0]


def test_completing_one_job_queues_exactly_one_full_run():
    job_id, batch_id = "job-test", "batch-test"
    batch = service.Batch(id=batch_id, node_id="10", run_each=True,
                          template=template(), workflow=None, client_id="client")
    batch.jobs.append(job_id)
    service.BATCHES[batch_id] = batch
    service.JOBS[job_id] = service.Job(id=job_id, batch_id=batch_id, index=0)

    class Queue:
        def __init__(self): self.items = []
        def put(self, item): self.items.append(item)

    fake_server = types.SimpleNamespace(number=0, prompt_queue=Queue())
    async def validate(_id, prompt, targets=None):
        assert targets is None
        assert prompt["10"]["inputs"]["enhanced_prompt"] == "enhanced text"
        return ["20"]
    with mock.patch.object(service, "_server", return_value=fake_server), \
         mock.patch.object(service, "_validate", side_effect=validate):
        asyncio.run(service._complete(job_id, "enhanced text", ""))
        asyncio.run(service._complete(job_id, "enhanced text", ""))
    assert len(fake_server.prompt_queue.items) == 1
    assert service.JOBS[job_id].state == "full_queued"
    service.JOBS.pop(job_id)
    service.BATCHES.pop(batch_id)


def test_disabled_full_run_never_queues():
    job_id, batch_id = "job-off", "batch-off"
    batch = service.Batch(id=batch_id, node_id="10", run_each=False,
                          template=template(), workflow=None, client_id=None)
    batch.jobs.append(job_id)
    service.BATCHES[batch_id] = batch
    service.JOBS[job_id] = service.Job(id=job_id, batch_id=batch_id, index=0)
    asyncio.run(service._complete(job_id, "text", ""))
    assert service.JOBS[job_id].state == "enhanced"
    service.JOBS.pop(job_id)
    service.BATCHES.pop(batch_id)
