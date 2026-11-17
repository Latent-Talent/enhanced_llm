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
3. Select (or edit) an Enhancement Preset, whose text is supplied as the LLM system prompt. Optionally expand **Jailbreak** to prepend a separate custom instruction block before those preset instructions.
4. Choose an enhancement count from 1 to 32.
5. Set **Queue Run for Each** (default Off).
6. Click Enhance Prompt. Each enhancement is queued as a partial graph run consisting of the node and its upstream dependencies. The button displays progress (`Cancel · 2/5` while running) and reverts to `Enhance` with no counter after completion or cancellation. Click Cancel to cancel outstanding jobs from this enhancement batch only.
7. Result text is appended to the active prompt set.
8. With the toggle On, every successful enhancement automatically queues ONE full workflow using that specific result. The full run joins ComfyUI's standard queue, does not skip other queued jobs, and does not run the enhancement LLM again.

The node's normal workflow execution is pass-through: it outputs the selected enhanced prompt (or the original prompt when no enhancement has been stored).

## Interface

- Original prompt and Enhance Prompt count/action, with `x/y` progress displayed directly on the button and no persistent status footer. The button becomes **Cancel** while enhancements remain; cancellation targets only the active batch and leaves already queued full runs intact.
- **Queue Run for Each**: a visible on/off switch directly beneath Enhance Prompt; off by default. Exactly one full workflow per successful enhancement when enabled; never for failed enhancements.
- Enhanced prompt textarea, browsing, removal, undo/redo and clear. Resizing any visible textarea also adjusts the node height, and field heights are saved with the workflow.
- **Completed LLM queue titles:** Enhancement-only jobs publish a genuine inline text preview labeled `LLM Enhanced 1/5`, `LLM Enhanced 2/5`, etc., instead of the generic `Job #xx`. This uses ComfyUI's native Jobs API and the text preview's display filename, without writing files or changing ComfyUI's queue components. Clicking **View** opens the generated enhanced text. Full workflow executions do not receive this text label and continue showing their real generated filenames.
- Prompt sets: save/rename, create, select, delete; stored in the ComfyUI workflow JSON.
- Prompt cycle: fixed, increment, decrement, shuffle and random.
- Shuffle and Random choose randomness automatically in the background. Shuffle visits every prompt once per shuffled cycle; the native LLM seed remains a separate generation control.
- Enhancement presets: 19 protected defaults grouped by Krea 2, MiniMax H3, and MOSS-Image, plus editable/savable user presets.
- The redundant native `system_prompt` input is removed: enhancement instructions are supplied by the chosen Enhancement Preset, optionally preceded by **Jailbreak** text. This optional prefix is stored as its own workflow input and does not overwrite a protected/default or user-created preset.
- **Single LLM seed control:** use the native `Sampling Mode → seed` field (or its connected upstream seed source). Each enhancement queues through ComfyUI's normal lifecycle; upstream seed nodes execute their configured queue-time behavior and update their visible state. Unconnected fixed seeds remain fixed. Prompt Cycle Random/Shuffle uses separate internal randomness and exposes no seed widget.

- **LLM Sampling presets:** Five descriptive, one-click recipes that update the *actual* native `max_length`, `Sampling Mode`, `temperature`, `top_k`, `top_p`, `min_p`, `repetition_penalty`, and `presence_penalty` controls. Presets do not change the native `seed`, or `thinking`, `use_default_template`, and `mtp`. Connected numeric input sockets are preserved; linked fields are reported and the selection shows Custom if the complete preset did not apply. Previously loaded workflows are never automatically overwritten.

### LLM sampling recipes

The sampling preset selector appears at the bottom of the enhancement panel, immediately before the native ComfyUI sampling controls. It applies changes immediately and includes a short usage explanation. Choosing a preset does **not** introduce another seed, model configuration, or separate sampler; it writes the native DynamicCombo child widgets named `sampling_mode.temperature`, etc. Manual changes show Custom when the picker is next opened.

| Preset | Best for | Max length | Temp | Top K | Top P | Min P | Repetition | Presence |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Faithful / Precise | preserving constraints, text and reference details | 1024 | .40 | 40 | .85 | .06 | 1.05 | .00 |
| Balanced / Recommended | most image and video prompt enhancements | 1024 | .70 | 64 | .92 | .05 | 1.05 | .00 |
| Creative / Detailed | richer imagery and artistic variation | 1536 | .90 | 80 | .95 | .03 | 1.05 | .00 |
| High Variety / Exploratory | exploring alternate prompt ideas | 1536 | 1.10 | 120 | .98 | .02 | 1.03 | .00 |
| Structured / Long Output | lengthy or sectioned MiniMax H3 prompts | 2048 | .55 | 40 | .90 | .05 | 1.05 | .00 |

These settings are starting points, not universal optimums. `max_length` is an upper generation limit rather than an instruction to use all tokens. Low temperature generally produces more repeatable wording; high temperature allows greater variation and can drift from the source. For long H3 reference prompts, raise `max_length` further if outputs are truncated. All presets use Sampling Mode On.

### Factory presets

These are model/task-specific enhancement instructions, not separate image/video model settings.

**Krea 2 (7):** General; Photo; Anime; Illustration/Painting; 3D Render; Product Photography; Typography/Graphic Design.

**MOSS-Image (7):** General; Photo; Anime; Illustration/Concept Art; 3D/CGI; Product/Commercial; Typography/Design. MOSS-Image is an image model, not a video model. The natural-language graphic prompt is preferred unless the user explicitly supplies a structured model-facing layout specification.

**MiniMax H3 (5):** Text to Video (T2VA); First Frame (I2VA); First / Last Frame (FL2VA); Last Frame (L2VA); Reference (Ref2VA). The H3 presets include the correct mode-specific alignment instructions, image/audio reference labels and section structures.

The original preset IDs `default:krea2`, `default:moss`, and `default:h3` are preserved for previously saved workflows.

Official developer guidance used to design the prompts:
- [Krea 2 prompting](https://github.com/krea-ai/krea-2/blob/main/docs/prompting.md) and [prompt expansion](https://github.com/krea-ai/krea-2/blob/main/docs/expansion.txt)
- [MOSS-Image prompting and layout](https://github.com/OpenMOSS/MOSS-Image/blob/main/USERGUIDE.md)
- [MiniMax H3 prompt-writing modes](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/SKILL.md) and [reference format](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/references/ref-en.txt)

Factory defaults cannot be overwritten or deleted. To customize one, edit its instructions and use Save As to make a new user preset. User presets use ComfyUI's per-user data API.

## Queuing design

The Enhance button first reserves unique job IDs and an immutable full-workflow template on the server. Each partial enhancement is then queued through **ComfyUI's own `app.queuePrompt` lifecycle**. This invokes every upstream widget's `beforeQueued` and `afterQueued` callbacks, including connected seed-source nodes, rather than emulating an increment or random setting. The upstream seed node's normal queue-time UI updates remain visible. A server prompt hook maps each reserved job UUID to its real ComfyUI prompt ID for accurate cancellation and history lookups.

A successful result is saved and, if Queue Run for Each is enabled, triggers validation and submission of one full-workflow snapshot with that exact text. Unsubmitted reservations are closed after the frontend queue operation completes.

Automatically queued full runs include ComfyUI's native `create_time` (milliseconds since epoch), client ID and workflow metadata in the prompt's extra data. This is required for the modern `/api/jobs` list to sort these runs alongside native submissions rather than placing them behind older completed jobs while still counting them as active.


The queued full workflow disconnects the LLM-only upstream links (CLIP, multimodal inputs and system prompt) from the pass-through enhancer, reducing unnecessary model loading. Each enhancement job can only trigger its associated full run once, even on repeated completion signals.

The server-side coordinator stays alive while ComfyUI is running and does not require an open browser to enqueue full runs. Pending jobs do not survive a ComfyUI server restart, consistent with ComfyUI's in-memory execution queue.

### Limitations

- Up to 32 enhancements in one batch.
- The full workflow reflects the graph at the moment the batch was submitted; later edits do not modify already-reserved runs.
- Queue-time seed-node updates depend on that source node implementing ComfyUI's beforeQueued/afterQueued lifecycle. Execution-only state changes do not automatically update the browser widget. Enhancement batches cannot be submitted while a separate ComfyUI queue submission is in progress; queued execution jobs already running are unaffected.
- Browser-side prompt-set editing needs the browser open to receive/display incoming result events. The server-side automatic queuing is independent.
- Intended for a local/trusted ComfyUI server. Multiuser deployments should add per-user permission boundaries around the custom batch endpoint.
- Unit tests check the core behavior without needing a model or GPU; end-to-end UI/inference testing requires ComfyUI.

## Tests

    python -m pip install pytest aiohttp
    python tests/run_unit_tests.py
    node --test tests/frontend/*.test.mjs

## Files

- nodes.py: native text generation delegation and pass-through output.
- queue_service.py: partial batch queue and automatic follow-up full runs.
- web/main.js: scoped DOM controls and native ComfyUI app integration.
- web/cycle.mjs: deterministic prompt selection.
- web/presets.mjs: immutable built-in preset definitions.
- web/styles.css: custom controls styled to match ComfyUI.

### Queue job naming

ComfyUI's standard queue overlay does not currently expose a supported custom per-job title field. It renders generic pending/running statuses and completed filenames, so injecting a name into job metadata does not rename a queue row. A separate frontend queue integration would be needed for visible labels such as "Enhancement 1/5" and "Full Run 1/5"; this plugin does not monkey-patch ComfyUI's queue components.


### Original prompt as a STRING input

The Prompt field now has a **Use Input** button above its textarea. Select it
to replace the editable textarea with an input hint, then connect any STRING
output to the existing **prompt** socket on the left side of this node.
ComfyUI's native input handling passes the connected text into both manual
enhancement and normal pass-through workflows; no separate adapter or custom
text input type is required.

When a prompt input is connected, **Enhance** accepts it even if the stored
textarea is empty. **Use Text** disconnects the wire and restores the saved
textarea text. The **↑** Promote action also returns to text mode explicitly.
The selected display mode is stored with the workflow.

When **Queue Run for Each** is enabled, an automatically queued full run uses
its generated enhanced text and removes the original prompt's upstream link in
that *run's snapshot only*. The user's original connected graph remains unchanged.


### Queue-aware Enhance / Cancel button

The Enhance/Cancel counter now reflects live ComfyUI queue status for this node's
enhancement batch. Cancelled jobs, including jobs individually removed through
ComfyUI's own queue controls, are excluded from the **x/y** denominator.
Successful enhancements remain in the numerator. For example, a 5-job batch
with two completed and one externally cancelled displays **Cancel · 2/4**.
If no jobs remain active, the button returns to **Enhance**. An all-cancelled
batch returns immediately to Enhance when the queue status refreshes.

The server reconciles the actual pending/running queue and history after native
submission completes. A running enhancement interrupted through the native
ComfyUI queue is categorized as cancelled rather than as a failed generation.
Queue-run-for-each jobs are not counted as additional enhancement jobs.


The toolbar reacts to ComfyUI's native queue-status events (debounced to avoid
excess requests) as well as polling for recovery if an event is missed. Only
the originating enhancement batch affects this node's button.


### Native prompt socket layout

The Prompt input uses the original native ComfyUI STRING socket, anchored
beside the **Prompt** label in the custom control panel. Selecting **Use Input**
or connecting a STRING output removes the entire prompt textarea, as with
native widget conversion. It no longer displays a placeholder text field.
**Use Text** disconnects the wire and restores the saved textarea. The socket
position is updated from the DOM widget's actual layout on node arrangement
and resize, not the default top-of-node socket position.
