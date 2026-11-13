"""Request-scoped W4A16 matrix-multiply preference for native ComfyUI LLMs.

Not a checkpoint loader or a new kernel: this uses ComfyUI's own
MixedPrecisionOp full_precision_matrix_mult policy. We never modify quantized
weights or install custom operations.

The installed native ComfyUI format registry still decides which checkpoints
can load. Full precision is selected only for already recognized 4-bit
quantized layers; other layers retain their native optimized path.
"""

from __future__ import annotations

from contextlib import contextmanager
from importlib import import_module
import re
from typing import Any, Iterator

# These are *execution* choices, not a format compatibility allowlist.
MATRIX_PRECISION_MODES = ("native", "w4a16")


def is_native_four_bit_format(value: Any) -> bool:
    """Identify 4-bit weight formats by native metadata (not checkpoint name).

    The native engine's registry determines whether each format can load.
    The matching convention covers current NVFP4 and W4A4/W4A8 formats plus
    future explicitly named W4A16 or INT4 layouts, when upstream supports them.
    """
    if not isinstance(value, str):
        return False
    fmt = value.lower()
    return bool(
        fmt == "nvfp4"
        or re.search(r"(?:^|_)w4a\d+(?:_|$)", fmt)
        or re.search(r"(?:^|_)int4(?:_|$)", fmt)
    )


@contextmanager
def native_matrix_precision(clip: Any, mode: str = "native") -> Iterator[dict[str, Any]]:
    """Force *native* 4-bit dequantized BF16/FP16 matmul for one LLM call.

    The stock ComfyUI CLIP.generate() context normally switches eligible
    quantized layers to accelerated A4/A8 kernels. Setting
    _full_precision_mm_config makes that native context skip the selected
    layers; _full_precision_mm performs dequantization in the compute dtype.

    RUNTIME.run serializes calls from Enhanced LLM nodes. The flags are
    restored even on interrupt/error, so later requests use their own mode.
    """
    if mode not in MATRIX_PRECISION_MODES:
        raise ValueError(f"Invalid matrix precision mode {mode!r}: {MATRIX_PRECISION_MODES}")

    if mode == "native":
        yield {
            "mode": mode, "w4a16_layers": 0,
            "w4a16_formats": [], "activation_dtype": "native",
        }
        return

    stage = getattr(clip, "cond_stage_model", None)
    if not callable(getattr(stage, "modules", None)):
        raise ValueError("W4A16 requires a native ComfyUI CLIP model with quantized modules.")

    # Import lazily: testing and ordinary native mode do not require ComfyUI.
    mixed_precision_op = import_module("comfy.ops").MixedPrecisionOp
    modules = []
    dtypes = set()
    formats = set()
    for module in stage.modules():
        if not isinstance(module, mixed_precision_op):
            continue
        fmt = getattr(module, "quant_format", None)
        if not is_native_four_bit_format(fmt):
            continue
        if not all(hasattr(module, attr) for attr in ("_full_precision_mm", "_full_precision_mm_config")):
            raise ValueError(
                "This ComfyUI release has incompatible W4A16 control APIs. "
                "Update ComfyUI or select native mode."
            )
        factory_kwargs = getattr(module, "factory_kwargs", None)
        dtype = factory_kwargs.get("dtype") if isinstance(factory_kwargs, dict) else None
        if str(dtype) not in ("torch.float16", "torch.bfloat16"):
            raise ValueError(
                f"W4A16 requires FP16/BF16 activation compute, but native format "
                f"{fmt!r} uses {dtype!s}. Select native mode instead."
            )
        modules.append(module)
        dtypes.add(str(dtype).removeprefix("torch."))
        formats.add(fmt)

    if not modules:
        raise ValueError(
            "W4A16 mode requires a ComfyUI-compatible checkpoint containing native "
            "packed 4-bit linear layers. This option does not load unsupported AWQ/GPTQ "
            "checkpoint formats. Use native mode for other models."
        )

    previous = [(module, module._full_precision_mm, module._full_precision_mm_config)
                for module in modules]
    try:
        for module in modules:
            module._full_precision_mm = True
            module._full_precision_mm_config = True
        yield {
            "mode": mode,
            "w4a16_layers": len(modules),
            "w4a16_formats": sorted(formats),
            "activation_dtype": ",".join(sorted(dtypes)),
        }
    finally:
        for module, previous_mm, previous_config in previous:
            module._full_precision_mm = previous_mm
            module._full_precision_mm_config = previous_config
