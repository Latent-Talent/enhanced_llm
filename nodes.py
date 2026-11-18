"""Native Generate Text V2 wrapper with an explicit enhancement/pass-through mode.

The CLIP input is optional in the schema so a full workflow can consume an
already-generated prompt without re-loading the LLM's upstream model path.
"""
from comfy_api.latest import io
from comfy_extras.nodes_textgen import TextGenerateV2

from .queue_service import enhancement_title, finish_job

NODE_ID = "LatentTalentEnhancedGenerateText"


class EnhancedGenerateText(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        native = TextGenerateV2.define_schema()
        inputs = []
        prompt_socket = io.String.Input(
            "prompt_input",
            display_name="prompt",
            force_input=True,
            optional=True,
            tooltip="Optional external STRING prompt. Overrides the editable Prompt field when connected.",
        )
        for item in native.inputs:
            if item.id == "system_prompt":
                # enhancement_text is the node's only system prompt input.
                continue
            if item.id == "clip":
                inputs.append(io.Clip.Input("clip", optional=True))
            else:
                inputs.append(item)
            # Place the actual socket directly after native AUDIO inputs.
            # No LiteGraph widget geometry manipulation is necessary.
            if item.id == "audios":
                inputs.append(prompt_socket)
            if item.id == "prompt":
                inputs.extend([
                    io.String.Input("enhanced_prompt", multiline=True, default=""),
                    io.String.Input("enhanced_thinking", multiline=True, default=""),
                    io.String.Input("enhancement_text", multiline=True, default=""),
                    io.String.Input("jailbreak_text", multiline=True, default=""),
                    io.String.Input("enhancement_preset_id", default="default:krea2"),
                    io.String.Input("prompt_sets_json", multiline=True,
                                    default='{"version":1,"sets":[{"name":"Unsaved","items":[],"step":0}],"active":0,"index":0}'),
                    io.Combo.Input("prompt_cycle", options=[
                        "fixed", "increment", "decrement", "shuffle", "random"], default="fixed"),
                    io.Boolean.Input("queue_run_for_each", default=False),
                    io.String.Input("ui_action", default="pass"),
                    io.String.Input("enhancement_job_id", default=""),
                ])
        if not any(item.id == "prompt_input" for item in inputs):
            # Keep the socket if an upstream native ComfyUI release renames
            # or removes the multi-audio input group.
            inputs.append(prompt_socket)
        return io.Schema(
            node_id=NODE_ID,
            display_name="Generate Text + Enhance",
            description="Enhance via native ComfyUI LLM, manage prompt sets and optionally queue a run for each result.",
            category="text/Enhanced LLM",
            search_aliases=["LLM", "prompt enhancer", "Krea 2", "MiniMax H3", "MOSS"],
            inputs=inputs,
            outputs=[
                io.String.Output(display_name="generated_text"),
                io.String.Output(display_name="thinking"),
            ],
            is_output_node=True,
            not_idempotent=True,
        )

    @classmethod
    def execute(cls, clip=None, prompt="", max_length=512, sampling_mode=None,
                enhanced_prompt="", enhanced_thinking="", enhancement_text="", jailbreak_text="",
                prompt_input=None,
                enhancement_preset_id="default:krea2", prompt_sets_json="",
                prompt_cycle="fixed", queue_run_for_each=False,
                ui_action="pass", enhancement_job_id="",
                thinking=False, use_default_template=True,
                mtp="auto", images=None, videos=None, audios=None,
                **_extra) -> io.NodeOutput:
        # An attached STRING socket takes priority. Empty connected strings
        # remain empty and are validated below instead of silently using a
        # stale local Prompt field.
        source_prompt = prompt_input if prompt_input is not None else prompt
        if ui_action != "enhance":
            # Normal workflow execution never invokes clip.generate().
            return io.NodeOutput(enhanced_prompt or source_prompt, enhanced_thinking if enhanced_prompt else "")

        if clip is None:
            raise ValueError("Connect a text-generation CLIP model before enhancing.")
        if not isinstance(source_prompt, str) or not source_prompt.strip():
            raise ValueError("Enter an original prompt or connect a nonempty STRING input before enhancing.")
        instructions = enhancement_text.strip()
        if not instructions:
            raise ValueError("Select or enter a nonempty enhancement system prompt.")
        # Optional instructions precede the selected preset in the LLM system prompt.
        # They do not alter the saved preset or the original user prompt.
        prefix = (jailbreak_text or "").strip()
        if prefix:
            instructions = prefix + "\n\n" + instructions

        # The native Sampling Mode > seed widget is the sole generation seed.
        # The queue manager offsets it per enhancement in a batch, without
        # changing the saved widget value or introducing a second seed input.
        sampling = dict(sampling_mode or {"sampling_mode": "on"})

        generated = TextGenerateV2.execute(
            clip=clip,
            prompt=source_prompt,
            max_length=max_length,
            sampling_mode=sampling,
            thinking=thinking,
            use_default_template=True,  # a system prompt requires a chat template
            mtp=mtp,
            system_prompt=instructions,
            images=images,
            videos=videos,
            audios=audios,
        )
        result, reasoning = generated.args[:2]
        result = str(result).strip()
        reasoning = str(reasoning).strip()
        if not result:
            raise ValueError("The language model returned an empty enhancement.")

        if enhancement_job_id:
            # Schedule any downstream full run without waiting on browser/WebSocket.
            finish_job(enhancement_job_id, result, reasoning)
        return io.NodeOutput(
            result,
            reasoning,
            ui={
                "enhanced_llm": [{
                    "job_id": enhancement_job_id,
                    "text": result,
                    "thinking": reasoning,
                }],
                # ComfyUI's /api/jobs uses the inline text preview's filename
                # as the completed job label. Supplying 'content' allows View
                # to show the prompt without saving a fictitious file.
                # This UI metadata is emitted ONLY on enhancement executions;
                # normal workflow runs retain their own output filenames.
                "text": [{
                    "filename": enhancement_title(enhancement_job_id),
                    "filenameIsDisplayName": True,
                    "content": result,
                }],
            },
        )
