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


def input_factory(type_name):
    return types.SimpleNamespace(
        Input=lambda id, **opts: types.SimpleNamespace(id=id, kind=type_name, **opts),
        Output=lambda display_name=None, **opts: types.SimpleNamespace(
            display_name=display_name, kind=type_name, **opts),
    )

fake_io = types.SimpleNamespace(
    ComfyNode=object, NodeOutput=NodeOutput,
    Int=input_factory("INT"), String=input_factory("STRING"),
    Clip=input_factory("CLIP"), Combo=input_factory("COMBO"),
    Boolean=input_factory("BOOLEAN"),
    Schema=lambda **kwargs: types.SimpleNamespace(**kwargs),
)
sys.modules["comfy_api"] = types.ModuleType("comfy_api")
api = types.ModuleType("comfy_api.latest")
api.io = fake_io
sys.modules["comfy_api.latest"] = api

sys.modules["comfy_extras"] = types.ModuleType("comfy_extras")
native = types.ModuleType("comfy_extras.nodes_textgen")
native.TextGenerateV2 = type("TextGenerateV2", (), {
    "execute": lambda **kw: None,
    "define_schema": classmethod(lambda cls: types.SimpleNamespace(inputs=[
        types.SimpleNamespace(id=k) for k in (
            "clip", "prompt", "system_prompt", "max_length", "sampling_mode", "thinking", "mtp"
        )
    ]))
})
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


def test_schema_hides_duplicate_system_prompt_and_adds_llm_seed_socket():
    schema = module.EnhancedGenerateText.define_schema()
    ids = [field.id for field in schema.inputs]
    assert "system_prompt" not in ids
    assert "enhancement_text" in ids
    assert "llm_seed" in ids
    assert "enhancement_index" in ids
    seed_input = next(field for field in schema.inputs if field.id == "llm_seed")
    assert seed_input.force_input is True
    assert seed_input.optional is True


def test_optional_llm_seed_overrides_native_seed_without_mutating_widget():
    calls = []
    def fake_generate(**kwargs):
        calls.append(kwargs)
        return NodeOutput("revised", "")
    module.TextGenerateV2.execute = fake_generate
    original = {"sampling_mode":"on", "seed":5}
    result = module.EnhancedGenerateText.execute(
        clip=object(), prompt="original", enhancement_text="expand",
        ui_action="enhance", sampling_mode=original,
        llm_seed=987, enhancement_index=3,
    )
    assert result.args[0] == "revised"
    assert calls[-1]["sampling_mode"]["seed"] == 990
    assert original["seed"] == 5

    module.EnhancedGenerateText.execute(
        clip=object(), prompt="original", enhancement_text="expand",
        ui_action="enhance", sampling_mode=original,
    )
    assert calls[-1]["sampling_mode"]["seed"] == 5
