"""Legacy-compatible ComfyUI node declarations for a native inference backend.

The node API is kept deliberately small. Model loading and token generation
delegate to the installed native ComfyUI implementation.
"""

from __future__ import annotations

import json

from .native import MTP_MODES, MATRIX_PRECISION_MODES, available_clip_types, generate_native, mtp_head_present, quantization_diagnostics
from .runtime import ModelRef, RUNTIME
from .version import __version__

CATEGORY = "Enhanced LLM"


class EnhancedLLMLoad:
    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths

        return {
            "required": {
                "model": (folder_paths.get_filename_list("text_encoders"), {
                    "tooltip": "Native ComfyUI text-encoder checkpoint. Quantization is detected by ComfyUI."
                }),
                "clip_type": (available_clip_types(), {"default": "auto",
                    "tooltip": "auto uses ComfyUI checkpoint architecture detection. Other values are native CLIPType choices."}),
            },
            "optional": {
                "cached_models": ("INT", {"default": 2, "min": 0, "max": 16,
                    "tooltip": "Max cached Python model references. This does NOT pin GPU memory; ComfyUI manages VRAM."}),
            },
        }

    RETURN_TYPES = ("ENHANCED_LLM", "STRING")
    RETURN_NAMES = ("llm", "model_name")
    FUNCTION = "load"
    CATEGORY = CATEGORY
    DESCRIPTION = "Select a native ComfyUI LLM; actual loading is lazy and shared."

    def load(self, model, clip_type="auto", cached_models=2):
        import folder_paths

        path = folder_paths.get_full_path_or_raise("text_encoders", model)
        RUNTIME.configure(cached_models)
        return (ModelRef(path=path, clip_type=clip_type), model)


class EnhancedLLMFromCLIP:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"clip": ("CLIP",)}}

    RETURN_TYPES = ("ENHANCED_LLM",)
    RETURN_NAMES = ("llm",)
    FUNCTION = "wrap"
    CATEGORY = CATEGORY
    DESCRIPTION = "Use an existing native ComfyUI CLIP loader without reloading its model."

    def wrap(self, clip):
        if not all(callable(getattr(clip, name, None)) for name in ("tokenize", "generate", "decode")):
            raise ValueError("This CLIP object does not expose native text generation.")
        return (ModelRef(borrowed_clip=clip),)


class EnhancedLLMGenerate:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "llm": ("ENHANCED_LLM",),
                "prompt": ("STRING", {"default": "", "multiline": True, "dynamicPrompts": True}),
                "max_tokens": ("INT", {"default": 512, "min": 1, "max": 32768}),
                "mtp": (list(MTP_MODES), {"default": "auto",
                    "tooltip": "Uses ComfyUI's native adaptive-tree MTP when compatible MTP weights are present."}),
                "sampling": (["on", "off"], {"default": "on"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            },
            "optional": {
                "matrix_precision": (list(MATRIX_PRECISION_MODES), {"default": "native",
                    "tooltip": "native uses ComfyUI optimized kernels; w4a16 keeps supported 4-bit weights packed, but uses BF16/FP16 matmul."}),
                "system_prompt": ("STRING", {"default": "", "multiline": True}),
                "thinking": ("BOOLEAN", {"default": False}),
                "use_default_template": ("BOOLEAN", {"default": True}),
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.01, "max": 2.0, "step": 0.01}),
                "top_k": ("INT", {"default": 64, "min": 0, "max": 1000}),
                "top_p": ("FLOAT", {"default": 0.95, "min": 0.0, "max": 1.0, "step": 0.01}),
                "min_p": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 1.0, "step": 0.01}),
                "repetition_penalty": ("FLOAT", {"default": 1.05, "min": 0.0, "max": 5.0, "step": 0.01}),
                "presence_penalty": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 5.0, "step": 0.01}),
                "image": ("IMAGE",),
                "video": ("IMAGE",),
                "audio": ("AUDIO",),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("text", "thinking", "info_json")
    FUNCTION = "generate"
    CATEGORY = CATEGORY
    DESCRIPTION = "Generate with native ComfyUI kernels and native MTP. All requests are serialized per process."

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Deliberately execute for every queued run; fixed seeds remain fixed.
        return float("nan")

    def generate(
        self, llm, prompt, max_tokens=512, mtp="auto", sampling="on", seed=0,
        system_prompt="", thinking=False, use_default_template=True,
        temperature=0.7, top_k=64, top_p=0.95, min_p=0.05,
        repetition_penalty=1.05, presence_penalty=0.0,
        image=None, video=None, audio=None, matrix_precision="native",
    ):
        if not isinstance(llm, ModelRef):
            raise TypeError("llm must come from Enhanced LLM Load or Enhanced LLM From CLIP.")

        def execute(clip):
            return generate_native(
                clip, prompt=prompt, max_tokens=max_tokens, mtp=mtp,
                matrix_precision=matrix_precision,
                do_sample=(sampling == "on"), seed=seed, system_prompt=system_prompt,
                thinking=thinking, use_default_template=use_default_template,
                temperature=temperature, top_k=top_k, top_p=top_p,
                min_p=min_p, repetition_penalty=repetition_penalty,
                presence_penalty=presence_penalty,
                image=image, video=video, audio=audio,
            )

        (text, thought, stats), reused = RUNTIME.run(llm, execute)
        stats["model_reference_reused"] = reused
        stats["version"] = __version__
        RUNTIME.remember(stats)
        return (text, thought, json.dumps(stats, sort_keys=True))


class EnhancedLLMStatus:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"refresh": ("BOOLEAN", {"default": False})},
                "optional": {"llm": ("ENHANCED_LLM",)}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status_json",)
    FUNCTION = "status"
    CATEGORY = CATEGORY
    DESCRIPTION = "Inspect reference cache and last request without polling GPU memory mid-generation."

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def status(self, refresh=False, llm=None):
        status = RUNTIME.status()
        status["version"] = __version__
        if llm is not None:
            if not isinstance(llm, ModelRef):
                raise TypeError("Expected ENHANCED_LLM.")
            status["selected_model"] = (
                "borrowed_clip" if llm.path is None else llm.path.rsplit("/", 1)[-1]
            )
            if llm.borrowed_clip is not None:
                status["selected_mtp_head_present"] = mtp_head_present(llm.borrowed_clip)
                status["selected_quantization"] = quantization_diagnostics(llm.borrowed_clip)
        return (json.dumps(status, sort_keys=True),)


class EnhancedLLMRelease:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"mode": (["selected", "all"], {"default": "selected"})},
                "optional": {"llm": ("ENHANCED_LLM",)}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("result_json",)
    FUNCTION = "release"
    CATEGORY = CATEGORY
    DESCRIPTION = "Drop cached Python references only; native ComfyUI manages actual GPU eviction."

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def release(self, mode="selected", llm=None):
        if mode == "selected" and llm is None:
            raise ValueError("Connect an LLM to release the selected cache entry.")
        count = RUNTIME.release(None if mode == "all" else llm)
        return (json.dumps({"released_cache_references": count,
                            "gpu_memory_owner": "ComfyUI ModelPatcher"}),)


from .enhancer import EnhancedLLMPromptEnhancer


NODE_CLASS_MAPPINGS = {
    "EnhancedLLMPromptEnhancer": EnhancedLLMPromptEnhancer,
    "EnhancedLLMLoad": EnhancedLLMLoad,
    "EnhancedLLMFromCLIP": EnhancedLLMFromCLIP,
    "EnhancedLLMGenerate": EnhancedLLMGenerate,
    "EnhancedLLMStatus": EnhancedLLMStatus,
    "EnhancedLLMRelease": EnhancedLLMRelease,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "EnhancedLLMPromptEnhancer": "Enhanced LLM • Prompt Enhancer",
    "EnhancedLLMLoad": "Enhanced LLM • Load Native Model",
    "EnhancedLLMFromCLIP": "Enhanced LLM • Use Existing CLIP",
    "EnhancedLLMGenerate": "Enhanced LLM • Generate (Native MTP)",
    "EnhancedLLMStatus": "Enhanced LLM • Runtime Status",
    "EnhancedLLMRelease": "Enhanced LLM • Release Cache References",
}
