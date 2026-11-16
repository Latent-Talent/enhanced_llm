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


def test_batch_reservation_does_not_mutate_upstream_or_local_seed():
    original = template()
    original["7"] = {"class_type": "ExternalSeed", "inputs": {
        "seed": 930, "control_after_generate": "randomize"}}
    original["10"]["inputs"]["sampling_mode"]["seed"] = ["7", 0]
    batch = service.reserve_batch("10", 3, False, original, None, "client")
    assert len(batch.jobs) == 3
    assert len(set(batch.jobs)) == 3
    assert all(service.JOBS[jid].state == "reserved" for jid in batch.jobs)
    assert batch.template["10"]["inputs"]["sampling_mode"]["seed"] == ["7", 0]
    assert batch.template["7"]["inputs"]["control_after_generate"] == "randomize"
    assert original["10"]["inputs"]["ui_action"] == "pass"
    assert original["7"]["inputs"]["seed"] == 930
    for jid in batch.jobs:
        service.JOBS.pop(jid)
    service.BATCHES.pop(batch.id)


def test_on_prompt_hook_maps_reservation_to_real_comfy_prompt_id():
    batch = service.reserve_batch("10", 1, True, template(), None, "client")
    job_id = batch.jobs[0]
    payload = {"prompt": template()}
    payload["prompt"]["10"]["inputs"]["ui_action"] = "enhance"
    payload["prompt"]["10"]["inputs"]["enhancement_job_id"] = job_id
    before_seed = payload["prompt"]["10"]["inputs"]["sampling_mode"]["seed"]
    updated = service._on_prompt_handler(payload)
    assert updated["prompt_id"] == job_id
    assert updated["prompt"]["10"]["inputs"]["sampling_mode"]["seed"] == before_seed
    assert service.JOBS[job_id].state == "pending"
    second = service._on_prompt_handler({"prompt": payload["prompt"]})
    assert "prompt_id" not in second
    service.JOBS.pop(job_id)
    service.BATCHES.pop(batch.id)


def test_finalize_closes_only_failed_reservations():
    batch = service.reserve_batch("10", 3, False, template(), None, None)
    accepted = batch.jobs[0]
    payload = {"prompt": template()}
    payload["prompt"]["10"]["inputs"].update(
        {"ui_action": "enhance", "enhancement_job_id": accepted}
    )
    service._on_prompt_handler(payload)
    service.finalize_batch(batch, [accepted])
    assert service.JOBS[accepted].state == "pending"
    assert [service.JOBS[j].state for j in batch.jobs[1:]] == ["error", "error"]
    try:
        service.finalize_batch(batch, ["unknown"])
    except ValueError:
        pass
    else:
        raise AssertionError("Finalization accepted foreign job ID")
    for jid in batch.jobs:
        service.JOBS.pop(jid)
    service.BATCHES.pop(batch.id)

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
    service.JOBS[job_id] = service.Job(id=job_id, batch_id=batch_id, index=0, state="pending")

    class Queue:
        def __init__(self): self.items = []
        def put(self, item): self.items.append(item)

    fake_server = types.SimpleNamespace(number=0, prompt_queue=Queue())
    async def validate(_id, prompt, targets=None):
        assert targets is None
        assert prompt["10"]["inputs"]["enhanced_prompt"] == "enhanced text"
        return ["20"]
    with (mock.patch.object(service, "_server", return_value=fake_server),
          mock.patch.object(service, "_validate", side_effect=validate)):
        asyncio.run(service._complete(job_id, "enhanced text", ""))
        asyncio.run(service._complete(job_id, "enhanced text", ""))
    assert len(fake_server.prompt_queue.items) == 1
    queued = fake_server.prompt_queue.items[0]
    # The Jobs API sorts by extra_data.create_time. Without it, a follow-up
    # run is pushed behind older history in the queue overlay even while
    # ComfyUI counts it as active.
    assert isinstance(queued[3]["create_time"], int)
    assert queued[3]["create_time"] > 1_600_000_000_000
    assert queued[3]["client_id"] == "client"
    assert service.JOBS[job_id].state == "full_queued"
    service.JOBS.pop(job_id)
    service.BATCHES.pop(batch_id)


def test_disabled_full_run_never_queues():
    job_id, batch_id = "job-off", "batch-off"
    batch = service.Batch(id=batch_id, node_id="10", run_each=False,
                          template=template(), workflow=None, client_id=None)
    batch.jobs.append(job_id)
    service.BATCHES[batch_id] = batch
    service.JOBS[job_id] = service.Job(id=job_id, batch_id=batch_id, index=0, state="pending")
    asyncio.run(service._complete(job_id, "text", ""))
    assert service.JOBS[job_id].state == "enhanced"
    service.JOBS.pop(job_id)
    service.BATCHES.pop(batch_id)


def test_cancel_targets_only_its_batch_and_prevents_auto_full_run():
    batch_id, job1, job2, unrelated = "cancel-batch", "cancel-one", "cancel-two", "other-job"
    batch = service.Batch(id=batch_id, node_id="10", run_each=True,
                          template=template(), workflow=None, client_id="client")
    batch.jobs.extend([job1, job2])
    service.BATCHES[batch_id] = batch
    for i, job_id in enumerate(batch.jobs):
        service.JOBS[job_id] = service.Job(id=job_id, batch_id=batch_id, index=i, state="pending")

    class Queue:
        def __init__(self):
            self.items = [(1, job1), (2, job2), (3, unrelated)]
            self.interrupts = []
        def delete_queue_item(self, predicate):
            for item in list(self.items):
                if predicate(item):
                    self.items.remove(item)
                    return True
            return False
        def interrupt_if_running(self, prompt_id):
            self.interrupts.append(prompt_id)
            return False

    fake_server = types.SimpleNamespace(prompt_queue=Queue())
    service.cancel_batch_jobs(batch, fake_server)
    assert batch.cancelled is True
    assert [item[1] for item in fake_server.prompt_queue.items] == [unrelated]
    assert set(fake_server.prompt_queue.interrupts) == {job1, job2}
    assert service.JOBS[job1].state == "cancelled"
    with mock.patch.object(service, "_server", return_value=fake_server):
        asyncio.run(service._complete(job1, "text", ""))
    assert [item[1] for item in fake_server.prompt_queue.items] == [unrelated]
    for job_id in batch.jobs:
        service.JOBS.pop(job_id)
    service.BATCHES.pop(batch_id)


def test_cancelling_while_full_run_validates_prevents_late_submission():
    batch_id, job_id = "late-batch", "late-job"
    batch = service.Batch(id=batch_id, node_id="10", run_each=True,
                          template=template(), workflow=None, client_id=None)
    batch.jobs.append(job_id)
    service.BATCHES[batch_id] = batch
    service.JOBS[job_id] = service.Job(id=job_id, batch_id=batch_id, index=0)

    class Queue:
        def __init__(self): self.items = []
        def put(self, item): self.items.append(item)
    fake_server = types.SimpleNamespace(number=0, prompt_queue=Queue())
    async def validate(_id, _graph, targets=None):
        batch.cancelled = True
        return ["20"]
    with (mock.patch.object(service, "_server", return_value=fake_server),
          mock.patch.object(service, "_validate", side_effect=validate)):
        asyncio.run(service._complete(job_id, "generated prompt", ""))
    assert fake_server.prompt_queue.items == []
    service.JOBS.pop(job_id)
    service.BATCHES.pop(batch_id)


def test_server_follow_up_submission_has_native_jobs_metadata():
    class Queue:
        def __init__(self):
            self.items = []
        def put(self, item):
            self.items.append(item)

    server = types.SimpleNamespace(number=45, prompt_queue=Queue())
    workflow = {"id": "workflow-xyz", "nodes": []}
    with mock.patch.object(service.time, "time", return_value=1795000000.25):
        service._put(server, "new-job-id", template(), ["20"], "client-123", workflow)
    assert server.number == 46
    item = server.prompt_queue.items[0]
    assert item[1] == "new-job-id"
    assert item[3]["create_time"] == 1795000000250
    assert item[3]["client_id"] == "client-123"
    assert item[3]["extra_pnginfo"]["workflow"] == workflow
    workflow["id"] = "modified-after-queue"
    assert item[3]["extra_pnginfo"]["workflow"]["id"] == "workflow-xyz"
    assert item[4] == ["20"]
