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


## Prompt Enhancer (0.2.0-alpha)

**Enhanced LLM • Prompt Enhancer** is a new node inspired by the former GGUF Prompt Enhancer's features, but is a clean native ComfyUI implementation. It shares the same model reference cache and native MTP engine as **Enhanced LLM • Generate**.

Connect **Enhanced LLM • Load Native Model** (or **Use Existing CLIP**) to the Prompt Enhancer's **llm** input. Source **prompt** is never overwritten by enhancement. The **enhanced_prompt** field is editable and the node outputs both the active enhanced prompt and the original prompt.

**Manual Enhance:** Click **Enhance Prompt** in the node's control panel. This submits one ComfyUI queue item containing only the Prompt Enhancer and its upstream model/media dependencies; it never queues the entire downstream image/video workflow. Batch Count supports 1–64 generations with consecutive request seeds. Multiple results append to the list, even when Overwrite Enhanced is selected.

**Prompt history:** The history lives in the node's serialized `history_json` field (a JSON array) with an active index. Prev/Next, Delete, Clear, Undo/Redo (20 states), and **Use Enhanced as Prompt** are available in the in-node toolbar. History persists with the workflow and can be inspected or modified in saved workflow JSON.

**Prompt Cycle:** Fixed, Increment, Decrement, Shuffle (no repeats within a deck), Random. Non-fixed modes use ComfyUI's native Control After Generate widget to advance a serialized cycle counter; the Python node resolves that counter into the selected prompt. The seed for LLM enhancement is independent: normal stored-prompt workflow runs do not advance the enhancement seed. With **Enhance with Workflow** enabled, each workflow run invokes the LLM; otherwise the node returns its selected stored prompt without loading the LLM.

**Presets and Prompt Sets:** The panel can load built-in enhancement instructions, save/edit user templates, and save/load/delete named prompt arrays. The bundled, newly authored templates include General, Krea 2 Image, and MiniMax H3 T2VA/I2VA/FL2VA/L2VA/Ref2VA. These are new examples, not the original GGUF project's template contents.

User data is saved under your ComfyUI **user directory** in `enhanced_llm/prompt_enhancer/templates` and `enhanced_llm/prompt_enhancer/prompt_sets`. Default templates are read-only.

**Multimodal:** Optional IMAGE reference and VIDEO-frame IMAGE input are forwarded to native ComfyUI generation. Native AUDIO input is exposed as well; actual supported modalities depend on the selected model/ComfyUI build.

**Notes and limitations:** Requires a modern ComfyUI frontend with `app.graphToPrompt` / `api.queuePrompt` for the manual Enhance button. The backend does not offer an out-of-band GPU inference endpoint. Queued and in-progress requests follow native ComfyUI cancellation; the frontend records results for temporarily inactive workflow tabs in memory and restores them when the graph remounts. Full persistent KV/DeltaNet conversation caching and live token streaming are not included in this version.

**Tests:**
```bash
python -m unittest discover -s tests -v
node --test tests/frontend/enhancer_state.test.mjs
```

No real-GPU ComfyUI smoke test has been performed yet.


### ComfyUI-style Prompt Enhancer controls (0.2.1-alpha)

The Prompt Enhancer uses a compact, theme-aware in-node toolbar styled to match the modern ComfyUI interface, including the active light/dark palette. The main action is a prominent **Enhance** button (which changes to **Cancel** while a manual enhancement is queued). The panel retains previous/next prompt navigation, Undo/Redo, Prompt Sets, and template actions, while native ComfyUI input widgets retain their own appearance. This is a visual/UI update only; it does not require switching node renderers or running ComfyUI Nodes 2.0. A native **Enhance** button fallback is available on older frontends that do not support the embedded toolbar.
