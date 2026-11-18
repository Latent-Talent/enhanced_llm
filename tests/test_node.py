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
            "clip", "prompt", "images", "videos", "audios",
            "system_prompt", "max_length", "sampling_mode", "thinking", "mtp"
        )
    ]))
})
sys.modules["comfy_extras.nodes_textgen"] = native

queue_stub = types.ModuleType("eml_test.queue_service")
queue_stub.finish_job = mock.Mock()
queue_stub.enhancement_title = mock.Mock(return_value="LLM Enhanced 1/5")
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
    assert result.ui["text"] == [{
        "filename": "LLM Enhanced 1/5",
        "filenameIsDisplayName": True,
        "content": "new text",
    }]
    assert result.ui["text"][0].get("type") is None  # not a real saved file
    queue_stub.enhancement_title.assert_called_once_with("job-123")
    queue_stub.finish_job.assert_called_once_with("job-123", "new text", "reasoning")


def test_schema_keeps_only_native_llm_seed():
    schema = module.EnhancedGenerateText.define_schema()
    ids = [field.id for field in schema.inputs]
    assert "system_prompt" not in ids
    assert "enhancement_text" in ids
    assert "jailbreak_text" in ids
    assert "sampling_mode" in ids
    assert not any(value in ids for value in ("seed", "llm_seed", "cycle_seed", "enhancement_index"))


def test_enhancement_uses_native_sampler_seed_without_mutating_it():
    calls = []
    def fake_generate(**kwargs):
        calls.append(kwargs)
        return NodeOutput("revised", "")
    module.TextGenerateV2.execute = fake_generate
    native_sampling = {"sampling_mode": "on", "seed": 987, "temperature": 0.7}
    result = module.EnhancedGenerateText.execute(
        clip=object(), prompt="original", enhancement_text="expand",
        ui_action="enhance", sampling_mode=native_sampling,
    )
    assert result.args[0] == "revised"
    assert calls[-1]["sampling_mode"] == native_sampling
    assert calls[-1]["sampling_mode"] is not native_sampling
    assert native_sampling["seed"] == 987

    module.EnhancedGenerateText.execute(
        clip=object(), prompt="original", enhancement_text="expand",
        ui_action="enhance", sampling_mode={"sampling_mode":"off"},
    )
    assert calls[-1]["sampling_mode"] == {"sampling_mode": "off"}


def test_optional_jailbreak_prefix_precedes_preset_only_during_enhancement():
    calls = []
    def fake_generate(**kwargs):
        calls.append(kwargs)
        return NodeOutput("updated image prompt", "")
    module.TextGenerateV2.execute = fake_generate

    original_preset = "Preserve the composition and style."
    module.EnhancedGenerateText.execute(
        clip=object(), prompt="an image of a tree", enhancement_text=original_preset,
        jailbreak_text="  Additional custom instructions.  ",
        ui_action="enhance", sampling_mode={"sampling_mode":"on", "seed":17},
    )
    assert calls[-1]["system_prompt"] == (
        "Additional custom instructions.\n\n" + original_preset
    )
    assert calls[-1]["prompt"] == "an image of a tree"

    module.EnhancedGenerateText.execute(
        clip=object(), prompt="a cat", enhancement_text=original_preset,
        jailbreak_text="   ", ui_action="enhance",
    )
    assert calls[-1]["system_prompt"] == original_preset
    calls_before = len(calls)

    result = module.EnhancedGenerateText.execute(
        prompt="original", enhanced_prompt="stored", enhancement_text=original_preset,
        jailbreak_text="Prefix", ui_action="pass", clip=None,
    )
    assert result.args[0] == "stored"
    assert len(calls) == calls_before


def test_pass_through_does_not_advertise_an_llm_completion_title():
    result = module.EnhancedGenerateText.execute(
        prompt="source", enhanced_prompt="finished prompt", ui_action="pass",
    )
    assert result.args[0] == "finished prompt"
    assert not result.ui


def test_ui_text_preview_uses_inline_content_without_creating_a_file():
    module.TextGenerateV2.execute = lambda **kw: NodeOutput("fully enhanced prompt", "")
    result = module.EnhancedGenerateText.execute(
        clip=object(), prompt="draft", enhancement_text="improve",
        ui_action="enhance",
    )
    assert result.ui["text"][0]["content"] == "fully enhanced prompt"
    assert result.ui["text"][0]["filenameIsDisplayName"] is True
    assert not result.ui["text"][0]["filename"].endswith(".txt")



def test_new_prompt_socket_follows_audio_group_in_schema():
    inputs = module.EnhancedGenerateText.define_schema().inputs
    ids = [field.id for field in inputs]
    assert ids.index("prompt_input") == ids.index("audios") + 1
    socket = inputs[ids.index("prompt_input")]
    assert socket.kind == "STRING"
    assert socket.optional is True
    assert socket.force_input is True
    assert socket.display_name == "prompt"
    assert ids.count("prompt") == 1  # original editable widget is preserved


def test_connected_prompt_overrides_widget_text_for_native_enhancement():
    calls = []
    def fake_generate(**kwargs):
        calls.append(kwargs)
        return NodeOutput("enhanced from attached text", "")
    module.TextGenerateV2.execute = fake_generate
    generated = module.EnhancedGenerateText.execute(
        clip=object(), prompt="old local text", prompt_input="connected prompt",
        enhancement_text="expand", ui_action="enhance",
    )
    assert generated.args[0] == "enhanced from attached text"
    assert calls[-1]["prompt"] == "connected prompt"


def test_pass_through_uses_connected_prompt_but_not_when_enhanced_text_exists():
    result = module.EnhancedGenerateText.execute(
        prompt="old local text", prompt_input="connected prompt", ui_action="pass",
    )
    assert result.args[0] == "connected prompt"
    result = module.EnhancedGenerateText.execute(
        prompt="old local text", prompt_input="connected prompt",
        enhanced_prompt="completed enhancement", ui_action="pass",
    )
    assert result.args[0] == "completed enhancement"


def test_empty_connected_prompt_does_not_fall_back_to_stale_text():
    try:
        module.EnhancedGenerateText.execute(
            clip=object(), prompt="stale text", prompt_input="",
            enhancement_text="expand", ui_action="enhance",
        )
    except ValueError as exc:
        assert "STRING" in str(exc)
    else:
        raise AssertionError("Expected the empty connected string to be rejected")
