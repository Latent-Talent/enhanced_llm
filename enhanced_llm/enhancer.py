"""Native ComfyUI Prompt Enhancer: manual batches and optional workflow generation."""

from __future__ import annotations

import json
import time

from .enhancer_core import (
    CYCLE_MODES, DEFAULT_INSTRUCTIONS, MAX_BATCH, apply_generated,
    clean_generated, dumps_history, enhancement_system_prompt, normalize_index,
    parse_history, select_index,
)
from .enhancer_storage import templates
from .native import MTP_MODES, generate_native
from .runtime import ModelRef, RUNTIME


class EnhancedLLMPromptEnhancer:
    @classmethod
    def INPUT_TYPES(cls):
        labels = [r["label"] for r in templates()]
        default = "Default / General" if "Default / General" in labels else "Custom"
        return {
            "required": {
                "llm": ("ENHANCED_LLM",),
                "prompt": ("STRING", {"default": "", "multiline": True, "dynamicPrompts": False}),
                "enhanced_prompt": ("STRING", {"default": "", "multiline": True, "dynamicPrompts": False}),
                "enhancement_preset": (labels, {"default": default}),
                "enhancement_instructions": ("STRING", {
                    "default": DEFAULT_INSTRUCTIONS, "multiline": True, "dynamicPrompts": False}),
                "enhance_with_workflow": ("BOOLEAN", {"default": False}),
                "overwrite_enhanced": ("BOOLEAN", {"default": False,
                    "label_on": "overwrite active", "label_off": "add new"}),
                "prompt_cycle": (list(CYCLE_MODES), {"default": "fixed"}),
                "history_json": ("STRING", {"default": "[]", "multiline": False, "dynamicPrompts": False}),
                "active_index": ("INT", {"default": 0, "min": 0, "max": 511}),
                "cycle_counter": ("INT", {"default": 0, "min": 0, "max": 0x7fffffff,
                    "control_after_generate": True}),
                "cycle_seed": ("INT", {"default": 0, "min": 0, "max": 0x7fffffff}),
                "batch_count": ("INT", {"default": 1, "min": 1, "max": MAX_BATCH}),
                "manual_request": ("STRING", {"default": "", "multiline": False, "dynamicPrompts": False}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "max_tokens": ("INT", {"default": 512, "min": 1, "max": 32768}),
                "mtp": (list(MTP_MODES), {"default": "auto"}),
            },
            "optional": {
                "image": ("IMAGE",),
                "video": ("IMAGE",),
                "audio": ("AUDIO",),
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.01, "max": 2.0, "step": 0.01}),
                "top_k": ("INT", {"default": 64, "min": 0, "max": 1000}),
                "top_p": ("FLOAT", {"default": 0.95, "min": 0.0, "max": 1.0, "step": 0.01}),
                "min_p": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 1.0, "step": 0.01}),
                "repetition_penalty": ("FLOAT", {"default": 1.05, "min": 0.0, "max": 5.0, "step": 0.01}),
                "presence_penalty": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 5.0, "step": 0.01}),
                "thinking": ("BOOLEAN", {"default": False}),
                "state_id": ("STRING", {"default": "", "multiline": False, "dynamicPrompts": False}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("enhanced_prompt", "prompt", "history_json")
    FUNCTION = "output_prompts"
    OUTPUT_NODE = True
    CATEGORY = "Enhanced LLM"
    DESCRIPTION = (
        "Prompt enhancer powered by the shared native ComfyUI LLM engine. "
        "Manual enhancement uses targeted partial execution and supports image/video references."
    )

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        if kwargs.get("manual_request") or kwargs.get("enhance_with_workflow"):
            return float("nan")
        if kwargs.get("prompt_cycle", "fixed") != "fixed":
            return float("nan")
        return None

    def output_prompts(
        self, llm: ModelRef, prompt: str, enhanced_prompt: str = "",
        enhancement_preset: str = "Custom", enhancement_instructions: str = DEFAULT_INSTRUCTIONS,
        enhance_with_workflow: bool = False, overwrite_enhanced: bool = False,
        prompt_cycle: str = "fixed", history_json: str = "[]",
        active_index: int = 0, cycle_counter: int = 0, cycle_seed: int = 0,
        batch_count: int = 1, manual_request: str = "", seed: int = 0,
        max_tokens: int = 512, mtp: str = "auto",
        image=None, video=None, audio=None, temperature: float = 0.7,
        top_k: int = 64, top_p: float = 0.95, min_p: float = 0.05,
        repetition_penalty: float = 1.05, presence_penalty: float = 0.0,
        thinking: bool = False, state_id: str = "", unique_id=None,
    ):
        if not isinstance(llm, ModelRef):
            raise TypeError("Connect an Enhanced LLM native model or From CLIP node.")
        source = str(prompt or "")
        saved = parse_history(history_json)
        current = normalize_index(active_index, len(saved))
        mode = "manual" if manual_request else ("workflow" if enhance_with_workflow else "stored")
        index = select_index(
            prompt_cycle if mode == "stored" else "fixed",
            current, len(saved), cycle_counter, cycle_seed,
        )
        if mode == "stored":
            selected = saved[index] if saved else str(enhanced_prompt or "")
            output = selected if selected.strip() else source
            return {
                "ui": {"enhanced_llm_enhancer": [json.dumps({
                    "mode": mode, "state_id": state_id, "index": index,
                    "count": len(saved),
                })]},
                "result": (output, source, dumps_history(saved)),
            }

        if not source.strip():
            raise ValueError("Enter a source prompt before enhancement.")
        instructions = str(enhancement_instructions or "").strip() or DEFAULT_INSTRUCTIONS
        count = max(1, min(MAX_BATCH, int(batch_count))) if mode == "manual" else 1
        # A batch holds one native runtime lock and uses one model/settings snapshot.
        # ComfyUI remains solely responsible for model residency and GPU memory.
        def operation(clip):
            generated = []
            timings = []
            for i in range(count):
                answer, _thinking, stats = generate_native(
                    clip,
                    prompt=source,
                    system_prompt=enhancement_system_prompt(instructions),
                    use_default_template=True,
                    thinking=thinking,
                    max_tokens=max_tokens,
                    mtp=mtp,
                    do_sample=True,
                    temperature=temperature,
                    top_k=top_k,
                    top_p=top_p,
                    min_p=min_p,
                    repetition_penalty=repetition_penalty,
                    presence_penalty=presence_penalty,
                    seed=(int(seed) + i) & 0xffffffffffffffff,
                    image=image,
                    video=video,
                    audio=audio,
                )
                generated.append(clean_generated(answer))
                timings.append(stats["total_seconds"])
            return generated, timings

        start = time.perf_counter()
        (generated, timings), reused = RUNTIME.run(llm, operation)
        RUNTIME.remember({
            "operation": "prompt_enhance", "mode": mode, "batch_count": count,
            "mtp_requested": mtp, "total_seconds": round(time.perf_counter() - start, 4),
            "model_reference_reused": reused,
        })
        updated, updated_index = apply_generated(
            saved, current, generated, overwrite_enhanced and count == 1,
        )
        new_history = dumps_history(updated)
        payload = {
            "mode": mode,
            "state_id": str(state_id or ""),
            "request": str(manual_request or ""),
            "node_id": str(unique_id or ""),
            "prompts": generated,
            "history_json": new_history,
            "index": updated_index,
            "overwrite": bool(overwrite_enhanced and count == 1),
            "model_reference_reused": reused,
            "mtp_requested": mtp,
            "generation_seconds": [round(x, 4) for x in timings],
        }
        return {
            "ui": {"enhanced_llm_enhancer": [json.dumps(payload, ensure_ascii=False)]},
            "result": (generated[-1], source, new_history),
        }
