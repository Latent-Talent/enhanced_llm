# Enhanced LLM — native ComfyUI LLM nodes

A clean-sheet custom-node package for ComfyUI's **native** LLM engine. No llama.cpp server, GGUF runtime, privately allocated GPU memory, or copied inference kernels.

**Version: 0.1.0-alpha.** The initial release provides native loading, serialized inference, adaptive MTP controls, cooperative model reference caching, image/video/audio inputs, and diagnostics.

## Requirements

- A current ComfyUI build supporting native LLM text generation (the new Qwen3.x / Qwen3.5 engine and optimized kernels where available).
- A compatible native text-encoder checkpoint in ComfyUI's **models/text_encoders** directory (or an additional path configured for that model category).
- ComfyUI's own Python environment and its existing dependencies, including native Comfy-Kitchen when the chosen model requires it.

No extra pip packages or Python version changes are required by these nodes.

## Install

From the ComfyUI checkout:

```bash
cd ~/ComfyUI/custom_nodes
git clone git@github.com:Latent-Talent/enhanced_llm.git
```

Restart ComfyUI. The nodes appear under **Enhanced LLM**.

## Basic workflow

**Enhanced LLM • Load Native Model** → **Enhanced LLM • Generate (Native MTP)** → **Show Text** (or another string consumer).

Choose the model in the native ComfyUI **text_encoders** directory. The loader delegates architecture detection, quantization, dtype, and dynamic VRAM handling directly to `comfy.sd.load_clip`.

Alternatively, connect a native ComfyUI **CLIP Loader** output to **Enhanced LLM • Use Existing CLIP** and then to **Generate**. Only CLIP objects that support text generation can be used.

### MTP

- `auto` — native adaptive-tree MTP, when an MTP head exists.
- `off` — native non-speculative generation.
- `2`, `3`, `4`, `5` — fixed draft depths.
- `tree2s1`, `tree2s2`, `tree3s1`, `tree4s1m8` — native fixed trees.

The node passes the selected option through to ComfyUI's existing decoder. MTP only accelerates compatible models with the required prediction head. A compatible native model without an MTP head continues to work without speculation.

### Quantization

There is **no hardcoded quantization allowlist**. Enhanced LLM loads through ComfyUI's native loader with no forced dtype or weight re-quantization. Formats supported by the installed ComfyUI build can be used, subject to that engine's actual model and hardware compatibility. This applies to newer formats as ComfyUI adds them, without format-specific changes in this package when upstream APIs remain compatible.

The result JSON identifies native loading and reports quantization metadata if the model wrapper exposes it; lack of that metadata does **not** mean the checkpoint is unquantized.

### Memory behavior

ComfyUI's `ModelPatcher` remains responsible for GPU residency and dynamic offloading. This project **does not pin models in VRAM** or interfere with other image/video model memory allocations.

Enhanced LLM holds a configurable LRU cache of Python model references to avoid needless checkpoint reconstruction. The cache is distinct from GPU residency: ComfyUI may evict/offload model weights at any time. The **Release Cache References** node does not promise GPU memory has been freed.

Generation is serialized with an in-process lock. The output statistics are recorded after generation; the status node intentionally does not query GPU memory during decoding, avoiding dynamic-VRAM interactions.

**Current limitations:** True persistent KV/DeltaNet state, prefix caching, model pinning/VRAM preference policies, per-token MTP acceptance telemetry, an OpenAI API, prompt enhancement presets, streaming, priority preemption, and a custom frontend are not implemented in v0.1. Their implementation depends on stable native ComfyUI interfaces. The upstream state/prefix-cache proposals remain under review.

## Nodes

| Node | Function |
| --- | --- |
| Load Native Model | Lazy native model selection and reuse |
| Use Existing CLIP | Reuse an already loaded native CLIP object |
| Generate (Native MTP) | Native sampling, system prompt, thinking, MTP, IMAGE/VIDEO/AUDIO inputs |
| Runtime Status | Model reference cache, last generation, MTP and quantization diagnostics |
| Release Cache References | Drop owned Python model references; ComfyUI controls VRAM |

## Verify

Run the unit tests in a Python environment (no GPU needed for mocked tests):

```bash
python -m unittest discover -s tests -v
```

The unit suite verifies node contracts and in-process caching logic; it does **not** replace a real GPU smoke test against a ComfyUI install with a compatible model.

### Performance baseline

Compare the same model and prompt using `mtp=off` and `mtp=auto`. The `info_json` output gives wall time, model reference reuse and output tokens / native generation duration **including prefill**. This is not a pure decode tokens/sec measurement.

## Engineering principles

- The original GGUF nodes are a **feature reference only**; no code is copied.
- All weight quantization, inference kernels, MTP, and GPU memory allocation remain ComfyUI-owned.
- No speculative support claims for unreleased KV-state or prefix-cache APIs.
- Future adapters should be isolated and tested against native capability discovery, not model-name guesses.

License: MIT. See [LICENSE](LICENSE).
