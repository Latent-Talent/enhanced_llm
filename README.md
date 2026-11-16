# Enhanced LLM - Generate Text + Enhance

A fresh ComfyUI V3 custom node based on ComfyUI's native Generate Text V2 inference path. The native CLIP, image/video/audio, sampling, thinking and MTP controls remain available. A custom DOM interface adds a prompt enhancer, result sets, cycling and optional full-run queuing.

## Installation

    cd ~/ComfyUI/custom_nodes
    git clone https://github.com/Latent-Talent/enhanced_llm.git

Restart ComfyUI. Add **text → Enhanced LLM → Generate Text + Enhance**.

Requires a recent ComfyUI containing TextGenerateV2 and ComfyUI V3 custom node support.

## How to use

1. Connect a text-generation CLIP model to the node.
2. Enter an original prompt.
3. Select (or edit) an Enhancement Preset, whose text is supplied as the LLM system prompt.
4. Choose an enhancement count from 1 to 32.
5. Set **Queue Run for Each** (default Off).
6. Click Enhance Prompt. Each enhancement is queued as a partial graph run consisting of the node and its upstream dependencies.
7. Result text is appended to the active prompt set.
8. With the toggle On, every successful enhancement automatically queues ONE full workflow using that specific result. The full run joins ComfyUI's standard queue, does not skip other queued jobs, and does not run the enhancement LLM again.

The node's normal workflow execution is pass-through: it outputs the selected enhanced prompt (or the original prompt when no enhancement has been stored).

## Interface

- Original prompt and Enhance Prompt count/action.
- **Queue Run for Each**: exactly one full workflow per successful enhancement; never for failed enhancements.
- Enhanced prompt textarea, browsing, removal, undo/redo and clear.
- Prompt sets: save/rename, create, select, delete; stored in the ComfyUI workflow JSON.
- Prompt cycle: fixed, increment, decrement, shuffle and random.
- Cycle seed: independent of the LLM sampling seed. Shuffle and random are deterministic.
- Enhancement presets: three protected defaults plus editable/savable user presets.

### Factory presets

- Default / Krea 2 - Image
- Default / MiniMax H3 - Video
- Default / MOSS - Video

Factory defaults cannot be overwritten or deleted. To customize one, edit its instructions and use Save As to make a new user preset. User presets use ComfyUI's per-user data API.

## Queuing design

The Enhance button takes one immutable workflow snapshot and sends it to a server-side queue bridge. The bridge validates and queues the chosen number of partial LLM executions, using distinct IDs and successive native sampling seeds. A successful result is saved and, if Queue Run for Each is enabled, triggers validation and submission of one full-workflow snapshot with that exact text.

The queued full workflow disconnects the LLM-only upstream links (CLIP, multimodal inputs and system prompt) from the pass-through enhancer, reducing unnecessary model loading. Each enhancement job can only trigger its associated full run once, even on repeated completion signals.

The server-side coordinator stays alive while ComfyUI is running and does not require an open browser to enqueue full runs. Pending jobs do not survive a ComfyUI server restart, consistent with ComfyUI's in-memory execution queue.

### Limitations

- Up to 32 enhancements in one batch.
- The full workflow reflects the graph at the moment the batch was submitted; later edits do not modify already-reserved runs.
- Browser-side prompt-set editing needs the browser open to receive/display incoming result events. The server-side automatic queuing is independent.
- Intended for a local/trusted ComfyUI server. Multiuser deployments should add per-user permission boundaries around the custom batch endpoint.
- Unit tests check the core behavior without needing a model or GPU; end-to-end UI/inference testing requires ComfyUI.

## Tests

    python -m pip install pytest aiohttp
    python -m pytest -q
    node --test tests/frontend/*.test.mjs

## Files

- nodes.py: native text generation delegation and pass-through output.
- queue_service.py: partial batch queue and automatic follow-up full runs.
- web/main.js: scoped DOM controls and native ComfyUI app integration.
- web/cycle.mjs: deterministic prompt selection.
- web/presets.mjs: immutable built-in preset definitions.
- web/styles.css: custom controls styled to match ComfyUI.
