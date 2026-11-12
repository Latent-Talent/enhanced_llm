"""Thin adapter around the installed ComfyUI text-encoder / LLM interfaces.

No private CUDA allocations, GGUF code, custom quantization implementations,
or monkeypatching of ComfyUI internals are performed here.
"""

from __future__ import annotations

import time
from typing import Any

MTP_MODES = ("auto", "off", "2", "3", "4", "5", "tree2s1", "tree2s2", "tree3s1", "tree4s1m8")


def available_clip_types() -> list[str]:
    """Use the installed ComfyUI CLIPType enum, not a frozen model allowlist."""
    import comfy.sd

    return ["auto"] + sorted(name.lower() for name in comfy.sd.CLIPType.__members__)


def load_native_clip(path: str, clip_type: str = "auto") -> Any:
    """Delegate architecture, dtype, quantization and offloading to ComfyUI."""
    import comfy.sd
    import folder_paths

    name = "STABLE_DIFFUSION" if clip_type == "auto" else clip_type.upper()
    try:
        selected = comfy.sd.CLIPType[name]
    except KeyError as exc:
        raise ValueError(
            f"ComfyUI does not recognize CLIP type {clip_type!r}. "
            "Choose a type exposed by the installed ComfyUI version."
        ) from exc

    return comfy.sd.load_clip(
        ckpt_paths=[path],
        embedding_directory=folder_paths.get_folder_paths("embeddings"),
        clip_type=selected,
        model_options={},  # Native ComfyUI decides quantization and dtype.
    )


def requested_mtp(value: str) -> bool | str:
    if value not in MTP_MODES:
        raise ValueError(f"Unsupported MTP mode {value!r}; available modes: {', '.join(MTP_MODES)}")
    return {"auto": True, "off": False}.get(value, value)


def mtp_head_present(clip: Any) -> bool | None:
    """Best-effort diagnostic only. Do not gate native MTP on this probe."""
    stage = getattr(clip, "cond_stage_model", None)
    if stage is None:
        return None
    modules = getattr(stage, "modules", None)
    if not callable(modules):
        return None
    try:
        for module in modules():
            if getattr(module, "mtp", None) is not None:
                return True
        return False
    except (AttributeError, RuntimeError, TypeError):
        return None


def quantization_diagnostics(clip: Any) -> dict[str, Any]:
    """Report installed-engine metadata without guessing from filenames."""
    patcher = getattr(clip, "patcher", None)
    model = getattr(patcher, "model", None)
    candidates = [
        getattr(patcher, "model_options", None),
        getattr(model, "model_options", None),
    ]
    metadata = None
    for options in candidates:
        if isinstance(options, dict) and options.get("quantization_metadata") is not None:
            metadata = options["quantization_metadata"]
            break

    details: dict[str, Any] = {
        "loader": "comfy.sd.load_clip",
        "format_selection": "native_auto",
        "metadata_present": metadata is not None,
    }
    if isinstance(metadata, dict):
        # A checkpoint can have thousands of per-layer records. Never serialize it all.
        details["metadata_entries"] = len(metadata)
        details["metadata_keys_sample"] = sorted(map(str, metadata))[:16]
    elif metadata is not None:
        details["metadata_type"] = type(metadata).__name__
    return details


def split_reasoning(decoded: str, prompt: str, tokens: Any, clip: Any) -> tuple[str, str]:
    """Match the native Generate Text convention for separate thinking output."""
    reasoning, separator, answer = decoded.partition("</think>")
    if separator:
        return answer.strip(), reasoning.replace("<think>", "", 1).strip()
    if reasoning.lstrip().startswith("<think>"):
        return "", reasoning.replace("<think>", "", 1).strip()

    # The native tokenizer can open a thinking block in its prompt template.
    # Only treat unmatched output as thinking if the prompt suffix confirms it.
    try:
        batch = next(iter(tokens.values())) if isinstance(tokens, dict) else tokens
        ids = [item[0] for item in batch[-1] if isinstance(item, tuple) and isinstance(item[0], int)]
        if prompt.rstrip().endswith("<think>") or clip.decode(ids[-4:]).rstrip().endswith("<think>"):
            return "", decoded.strip()
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        pass
    return decoded.strip(), ""


def tokenize_native(
    clip: Any,
    prompt: str,
    *,
    system_prompt: str = "",
    thinking: bool = False,
    use_default_template: bool = True,
    image: Any = None,
    video: Any = None,
    audio: Any = None,
) -> Any:
    images = []
    if image is not None:
        # IMAGE is a [batch, height, width, channels] tensor.
        images = [image[i : i + 1] for i in range(image.shape[0])]
    return clip.tokenize(
        prompt,
        image=None,
        images=images,
        video=video,
        audio=audio,
        skip_template=not use_default_template,
        min_length=1,
        thinking=thinking,
        system_prompt=system_prompt if use_default_template else "",
    )


def generate_native(
    clip: Any,
    *,
    prompt: str,
    system_prompt: str = "",
    thinking: bool = False,
    use_default_template: bool = True,
    image: Any = None,
    video: Any = None,
    audio: Any = None,
    max_tokens: int = 512,
    mtp: str = "auto",
    do_sample: bool = True,
    temperature: float = 0.7,
    top_k: int = 64,
    top_p: float = 0.95,
    min_p: float = 0.05,
    repetition_penalty: float = 1.05,
    presence_penalty: float = 0.0,
    seed: int = 0,
) -> tuple[str, str, dict[str, Any]]:
    """Use CLIP.generate, the same native path as ComfyUI's Generate Text node."""
    if max_tokens < 1:
        raise ValueError("max_tokens must be positive")
    mode = requested_mtp(mtp)
    start = time.perf_counter()
    tokens = tokenize_native(
        clip, prompt, system_prompt=system_prompt, thinking=thinking,
        use_default_template=use_default_template, image=image, video=video, audio=audio,
    )
    prefill_ready = time.perf_counter()

    # ComfyUI owns dynamic VRAM loading, prefill, optimized kernels, MTP,
    # temporary KV/DeltaNet state, and normal memory reclamation.
    generated_ids = clip.generate(
        tokens,
        do_sample=do_sample,
        max_length=max_tokens,
        temperature=temperature,
        top_k=top_k,
        top_p=top_p,
        min_p=min_p,
        repetition_penalty=repetition_penalty,
        presence_penalty=presence_penalty,
        seed=seed,
        mtp=mode,
    )
    generation_finished = time.perf_counter()
    decoded = clip.decode(generated_ids)
    answer, reasoning = split_reasoning(decoded, prompt, tokens, clip)
    token_count = len(generated_ids) if hasattr(generated_ids, "__len__") else None
    wall = generation_finished - prefill_ready

    stats = {
        "engine": "comfy_native",
        "mtp_requested": mtp,
        "mtp_head_present": mtp_head_present(clip),
        "output_tokens": token_count,
        "total_seconds": round(time.perf_counter() - start, 4),
        "tokenization_seconds": round(prefill_ready - start, 4),
        "native_generate_seconds": round(wall, 4),
        "output_tokens_per_second_including_prefill": (
            round(token_count / wall, 2) if token_count is not None and wall > 0 else None
        ),
        "quantization": quantization_diagnostics(clip),
    }
    return answer, reasoning, stats
