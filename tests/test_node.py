"""Pass-through and native delegation tests without a GPU or ComfyUI install."""
import importlib.util
import pathlib
import sys
import types
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
package = types.ModuleType("eml_test")
package.__path__ = [str(ROOT)]
sys.modules["eml_test"] = package


class NodeOutput:
    def __init__(self, *args, ui=None):
        self.args = args
        self.ui = ui


fake_io = types.SimpleNamespace(ComfyNode=object, NodeOutput=NodeOutput)
sys.modules["comfy_api"] = types.ModuleType("comfy_api")
api = types.ModuleType("comfy_api.latest")
api.io = fake_io
sys.modules["comfy_api.latest"] = api

sys.modules["comfy_extras"] = types.ModuleType("comfy_extras")
native = types.ModuleType("comfy_extras.nodes_textgen")
native.TextGenerateV2 = type("TextGenerateV2", (), {"execute": lambda **kw: None})
sys.modules["comfy_extras.nodes_textgen"] = native

queue_stub = types.ModuleType("eml_test.queue_service")
queue_stub.finish_job = mock.Mock()
sys.modules["eml_test.queue_service"] = queue_stub

spec = importlib.util.spec_from_file_location("eml_test.nodes", ROOT / "nodes.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_full_run_returns_stored_text_without_model():
    result = module.EnhancedGenerateText.execute(
        prompt="original", enhanced_prompt="enhanced", enhanced_thinking="thought",
        ui_action="pass", clip=None,
    )
    assert result.args == ("enhanced", "thought")


def test_original_fallback_without_enhancement():
    result = module.EnhancedGenerateText.execute(
        prompt="original", enhanced_prompt="", ui_action="pass", clip=None,
    )
    assert result.args == ("original", "")


def test_enhancement_requires_clip():
    try:
        module.EnhancedGenerateText.execute(prompt="text", ui_action="enhance", enhancement_text="edit")
    except ValueError as exc:
        assert "CLIP" in str(exc)
    else:
        raise AssertionError("Missing CLIP should be rejected")


def test_native_generation_sends_result_to_queue_service():
    module.TextGenerateV2.execute = lambda **kw: NodeOutput("new text", "reasoning")
    result = module.EnhancedGenerateText.execute(
        clip=object(), prompt="text", ui_action="enhance",
        enhancement_text="expand", enhancement_job_id="job-123",
    )
    assert result.args == ("new text", "reasoning")
    assert result.ui["enhanced_llm"][0]["job_id"] == "job-123"
    queue_stub.finish_job.assert_called_once_with("job-123", "new text", "reasoning")
