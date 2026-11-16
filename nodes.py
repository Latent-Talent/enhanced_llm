"""Native Generate Text V2 wrapper with an explicit enhancement/pass-through mode.

The CLIP input is optional in the schema so a full workflow can consume an
already-generated prompt without re-loading the LLM's upstream model path.
"""
from comfy_api.latest import io
from comfy_extras.nodes_textgen import TextGenerateV2

from .queue_service import finish_job

NODE_ID = "LatentTalentEnhancedGenerateText"


class EnhancedGenerateText(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        native = TextGenerateV2.define_schema()
        inputs = []
        for item in native.inputs:
            if item.id == "system_prompt":
                # enhancement_text is the node's only system prompt input.
                continue
            if item.id == "clip":
                inputs.append(io.Clip.Input("clip", optional=True))
            else:
                inputs.append(item)
            if item.id == "prompt":
                inputs.extend([
                    io.String.Input("enhanced_prompt", multiline=True, default=""),
                    io.String.Input("enhanced_thinking", multiline=True, default=""),
                    io.String.Input("enhancement_text", multiline=True, default=""),
                    io.String.Input("jailbreak_text", multiline=True, default=""),
                    io.Int.Input("llm_seed", optional=True, force_input=True,
                                 min=0, max=0xffffffffffffffff,
                                 tooltip="Optional INT socket overriding the native sampling seed for LLM generation."),
                    io.Int.Input("enhancement_index", default=0, min=0, max=31),
                    io.String.Input("enhancement_preset_id", default="default:krea2"),
                    io.String.Input("prompt_sets_json", multiline=True,
                                    default='{"version":1,"sets":[{"name":"Unsaved","items":[],"step":0}],"active":0,"index":0}'),
                    io.Combo.Input("prompt_cycle", options=[
                        "fixed", "increment", "decrement", "shuffle", "random"], default="fixed"),
                    io.Int.Input("cycle_seed", default=0, min=0, max=2147483647),
                    io.Boolean.Input("queue_run_for_each", default=False),
                    io.String.Input("ui_action", default="pass"),
                    io.String.Input("enhancement_job_id", default=""),
                ])
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
                enhancement_preset_id="default:krea2", prompt_sets_json="",
                prompt_cycle="fixed", cycle_seed=0, queue_run_for_each=False,
                ui_action="pass", enhancement_job_id="",
                llm_seed=None, enhancement_index=0,
                thinking=False, use_default_template=True,
                mtp="auto", images=None, videos=None, audios=None,
                **_extra) -> io.NodeOutput:
        if ui_action != "enhance":
            # Normal workflow execution never invokes clip.generate().
            return io.NodeOutput(enhanced_prompt or prompt, enhanced_thinking if enhanced_prompt else "")

        if clip is None:
            raise ValueError("Connect a text-generation CLIP model before enhancing.")
        if not prompt.strip():
            raise ValueError("Enter an original prompt before enhancing.")
        instructions = enhancement_text.strip()
        if not instructions:
            raise ValueError("Select or enter a nonempty enhancement system prompt.")
        # Optional instructions precede the selected preset in the LLM system prompt.
        # They do not alter the saved preset or the original user prompt.
        prefix = (jailbreak_text or "").strip()
        if prefix:
            instructions = prefix + "\n\n" + instructions

        sampling = dict(sampling_mode or {"sampling_mode": "on"})
        if llm_seed is not None:
            # Separate LLM seed input; never use the prompt-cycle random seed.
            # Batch jobs increment the connected seed without changing the source node.
            sampling["seed"] = (int(llm_seed) + int(enhancement_index)) % (1 << 64)

        generated = TextGenerateV2.execute(
            clip=clip,
            prompt=prompt,
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
            ui={"enhanced_llm": [{
                "job_id": enhancement_job_id,
                "text": result,
                "thinking": reasoning,
            }]},
        )
