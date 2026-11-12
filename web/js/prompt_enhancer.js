/* Enhanced LLM Prompt Enhancer controls.
 * Native ComfyUI widgets are authoritative and serialize workflow state.
 * Manual enhancement submits ONE pruned partial-execution queue item.
 */
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import {
  parseHistory, clampIndex, appendResults, removeAt, pruneToUpstream,
} from "./enhancer_state.mjs";

const NODE_TYPE = "EnhancedLLMPromptEnhancer";
const API_ROOT = "/enhanced_llm/enhancer";
const pending = new Map();
const completed = new Set();
const journal = new Map();

const w = (node, name) => node?.widgets?.find(x => x.name === name) ?? null;
const value = (node, name, fallback = "") => w(node, name)?.value ?? fallback;
const freshId = () => globalThis.crypto?.randomUUID?.()
  ?? ("enh-" + Date.now() + "-" + Math.random().toString(36).slice(2));

function repaint(node) {
  node?.setDirtyCanvas?.(true, true);
  node?.graph?.setDirtyCanvas?.(true, true);
}
function markEdited(node) {
  node?.graph?.change?.();
  repaint(node);
}
function setValue(node, key, next, invoke = false) {
  const widget = w(node, key);
  if (!widget) return;
  if (widget.value === next) return;
  widget.value = next;
  if (invoke) widget.callback?.(next);
  markEdited(node);
}

function history(node) {
  const parsed = parseHistory(value(node, "history_json", "[]"));
  const visible = String(value(node, "enhanced_prompt", ""));
  return parsed.length ? parsed : (visible.trim() ? [visible] : []);
}
function index(node) { return clampIndex(value(node, "active_index", 0), history(node).length); }

function snapshot(node) {
  return { prompts: history(node), index: index(node) };
}
function rememberUndo(node) {
  const state = snapshot(node);
  node._ellmUndo ??= [];
  node._ellmRedo ??= [];
  const last = node._ellmUndo.at(-1);
  if (last && JSON.stringify(last) === JSON.stringify(state)) return;
  node._ellmUndo.push(state);
  if (node._ellmUndo.length > 20) node._ellmUndo.shift();
  node._ellmRedo.length = 0;
}

function writeHistory(node, prompts, active) {
  const list = parseHistory(prompts);
  const selected = clampIndex(active, list.length);
  node._ellmSyncing = true;
  try {
    setValue(node, "history_json", JSON.stringify(list));
    setValue(node, "active_index", selected);
    setValue(node, "enhanced_prompt", list[selected] ?? "");
  } finally {
    node._ellmSyncing = false;
  }
  refresh(node);
}

function choose(node, next) {
  const list = history(node);
  if (!list.length) return;
  writeHistory(node, list, (next + list.length) % list.length);
  setValue(node, "cycle_counter", 0);
}
function deleteActive(node) {
  if (!history(node).length) return;
  rememberUndo(node);
  const next = removeAt(history(node), index(node));
  writeHistory(node, next.prompts, next.index);
  setValue(node, "cycle_counter", 0);
}
function clearAll(node) {
  if (!history(node).length) return;
  rememberUndo(node);
  writeHistory(node, [], 0);
  setValue(node, "cycle_counter", 0);
}
function undo(node, redo = false) {
  const from = redo ? (node._ellmRedo ?? []) : (node._ellmUndo ?? []);
  if (!from.length) return;
  const otherName = redo ? "_ellmUndo" : "_ellmRedo";
  node[otherName] ??= [];
  node[otherName].push(snapshot(node));
  const previous = from.pop();
  writeHistory(node, previous.prompts, previous.index);
  setValue(node, "cycle_counter", 0);
}
function useEnhancedAsPrompt(node) {
  const text = String(value(node, "enhanced_prompt", "")).trim();
  if (text) setValue(node, "prompt", text, true);
}

function addGenerated(node, response) {
  if (!Array.isArray(response.prompts) || !response.prompts.length) return;
  rememberUndo(node);
  const state = appendResults(
    history(node), index(node), response.prompts, Boolean(response.overwrite)
  );
  writeHistory(node, state.prompts, state.index);
  if (node._ellmPanel?.status) {
    node._ellmPanel.status.textContent =
      response.prompts.length === 1 ? "Enhanced prompt saved" :
      response.prompts.length + " enhanced prompts saved";
  }
}
function findActiveNode(id, nodeId) {
  const nodes = app.graph?._nodes ?? [];
  return nodes.find(n => n?.comfyClass === NODE_TYPE
    && String(value(n, "state_id")) === String(id)
    && (!nodeId || String(n.id) === String(nodeId)))
    ?? nodes.find(n => n?.comfyClass === NODE_TYPE && String(value(n, "state_id")) === String(id))
    ?? null;
}
function replay(node) {
  const id = String(value(node, "state_id"));
  const list = journal.get(id);
  if (!id || !list?.length) return;
  for (const result of list) addGenerated(node, result);
  journal.delete(id);
}

function notify(type, message) {
  const toast = app?.extensionManager?.toast;
  if (toast?.add) toast.add({ severity: type, summary: "Enhanced LLM", detail: message, life: 5500 });
  else (type === "error" ? console.error : console.info)("[Enhanced LLM]", message);
}

async function requestJSON(path, method = "GET", data = undefined) {
  const response = await api.fetchApi(API_ROOT + path, {
    method,
    ...(data === undefined ? {} : {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  });
  let payload = {};
  try { payload = await response.json(); } catch { /* malformed server body */ }
  if (!response.ok) throw new Error(payload.error || "Server returned HTTP " + response.status);
  return payload;
}

function setSelectOptions(select, items, selected) {
  if (!select) return;
  select.replaceChildren();
  for (const [name, label] of items) {
    const item = document.createElement("option");
    item.value = name;
    item.textContent = label;
    select.append(item);
  }
  if (items.some(([key]) => key === selected)) select.value = selected;
}

async function refreshTemplates(node) {
  try {
    const { templates } = await requestJSON("/templates");
    node._ellmTemplates = Array.isArray(templates) ? templates : [];
    const names = node._ellmTemplates.map(item => item.label);
    const widget = w(node, "enhancement_preset");
    if (widget?.options) widget.options.values = names;
    const panel = node._ellmPanel;
    if (!panel) return;
    setSelectOptions(panel.template, names.map(x => [x, x]), value(node, "enhancement_preset", "Custom"));
  } catch (error) {
    notify("error", "Unable to read enhancement templates: " + error.message);
  }
}

async function refreshSets(node) {
  try {
    const { prompt_sets } = await requestJSON("/sets");
    const panel = node._ellmPanel;
    if (!panel) return;
    const selected = panel.set.value;
    setSelectOptions(panel.set,
      [["", "Select saved set"], ...(prompt_sets ?? []).map(s => [s, s])], selected);
  } catch (error) {
    notify("error", "Unable to read Prompt Sets: " + error.message);
  }
}

function selectTemplate(node, label) {
  const record = (node._ellmTemplates ?? []).find(t => t.label === label);
  if (!record) return;
  setValue(node, "enhancement_preset", label);
  setValue(node, "enhancement_instructions", record.text);
  refresh(node);
}
async function saveTemplate(node) {
  const name = window.prompt("Save enhancement instructions as template (name):");
  if (!name) return;
  try {
    const record = await requestJSON("/templates/save", "POST", {
      name, instructions: String(value(node, "enhancement_instructions")),
    });
    setValue(node, "enhancement_preset", record.label);
    await refreshTemplates(node);
    notify("success", "Enhancement template saved");
  } catch (error) { notify("error", error.message); }
}
async function deleteTemplate(node) {
  const label = String(value(node, "enhancement_preset", ""));
  if (!label.startsWith("User / ")) {
    notify("warning", "Only user-created templates can be deleted");
    return;
  }
  if (!window.confirm("Delete " + label + "?")) return;
  try {
    await requestJSON("/templates/delete", "POST", { label });
    setValue(node, "enhancement_preset", "Custom");
    await refreshTemplates(node);
    notify("success", "Enhancement template deleted");
  } catch (error) { notify("error", error.message); }
}
async function saveSet(node) {
  const name = window.prompt("Save enhanced prompt array as Prompt Set (name):");
  if (!name) return;
  try {
    await requestJSON("/sets/save", "POST", {
      name, prompts: history(node), active_index: index(node),
    });
    await refreshSets(node);
    if (node._ellmPanel) node._ellmPanel.set.value = name.trim();
    notify("success", "Prompt Set saved");
  } catch (error) { notify("error", error.message); }
}
async function loadSet(node) {
  const name = node._ellmPanel?.set?.value;
  if (!name) return;
  try {
    const data = await requestJSON("/sets/load", "POST", { name });
    rememberUndo(node);
    writeHistory(node, data.prompts, data.active_index);
    setValue(node, "cycle_counter", 0);
    notify("success", "Prompt Set loaded");
  } catch (error) { notify("error", error.message); }
}
async function deleteSet(node) {
  const name = node._ellmPanel?.set?.value;
  if (!name || !window.confirm("Delete Prompt Set " + name + "?")) return;
  try {
    await requestJSON("/sets/delete", "POST", { name });
    await refreshSets(node);
    notify("success", "Prompt Set deleted");
  } catch (error) { notify("error", error.message); }
}

function syncCycleControl(node) {
  const nativeCounter = w(node, "cycle_counter");
  const control = nativeCounter?.linkedWidgets?.find(x =>
    typeof x.beforeQueued === "function" && typeof x.afterQueued === "function");
  if (!control) return;
  const automatic = !Boolean(value(node, "enhance_with_workflow", false))
    && value(node, "prompt_cycle", "fixed") !== "fixed";
  control.value = automatic ? "increment" : "fixed";
  if (control._ellmWrapped) return;
  control._ellmWrapped = true;
  const before = control.beforeQueued;
  const after = control.afterQueued;
  control.beforeQueued = function (...args) {
    syncCycleControl(node);
    if (String(value(node, "manual_request")) || Boolean(value(node, "enhance_with_workflow"))) return;
    return before?.apply(this, args);
  };
  control.afterQueued = function (...args) {
    syncCycleControl(node);
    if (String(value(node, "manual_request")) || Boolean(value(node, "enhance_with_workflow"))) return;
    return after?.apply(this, args);
  };
}

function onGenerated(e) {
  const detail = e?.detail ?? e;
  const raw = detail?.output?.enhanced_llm_enhancer;
  if (!Array.isArray(raw) || !raw.length) return;
  let data;
  try { data = typeof raw[0] === "string" ? JSON.parse(raw[0]) : raw[0]; }
  catch { return; }
  if (data?.mode === "stored" || !Array.isArray(data?.prompts)) return;
  const request = String(data.request || "");
  const token = request || ("workflow:" + String(detail?.prompt_id || freshId())
    + ":" + String(data.node_id || ""));
  if (completed.has(token)) return;
  completed.add(token);
  if (completed.size > 4096) completed.clear();

  const owner = request ? pending.get(request) : null;
  const live = findActiveNode(data.state_id, data.node_id);
  const target = live || owner?.node;
  if (target) addGenerated(target, data);
  if (!live && data.state_id) {
    const list = journal.get(data.state_id) ?? [];
    list.push(data);
    journal.set(data.state_id, list.slice(-64));
  }

  if (owner) {
    pending.delete(request);
    if (owner.node) {
      owner.node._ellmPending = null;
      refresh(owner.node);
    }
  }
}

async function cancelManual(node) {
  const state = node._ellmPending;
  if (!state) return;
  state.cancelRequested = true;
  if (state.jobId) {
    try {
      if (typeof api.cancelJob === "function") await api.cancelJob(state.jobId);
      else if (typeof api.interrupt === "function") await api.interrupt(state.jobId);
    } catch (error) { notify("error", error.message); }
  }
  pending.delete(state.request);
  node._ellmPending = null;
  setValue(node, "manual_request", "");
  refresh(node);
}

async function runManual(node) {
  if (node._ellmPending) { await cancelManual(node); return; }
  if (!String(value(node, "prompt")).trim()) {
    notify("warning", "Enter the original Prompt first");
    return;
  }
  if (!String(value(node, "enhancement_instructions")).trim()) {
    notify("warning", "Enhancement Instructions are empty");
    return;
  }
  if (typeof app.graphToPrompt !== "function" || typeof api.queuePrompt !== "function") {
    notify("error", "This ComfyUI frontend does not expose targeted prompt execution");
    return;
  }
  const request = freshId();
  const task = { request, node, jobId: null, cancelRequested: false };
  pending.set(request, task);
  node._ellmPending = task;
  setValue(node, "manual_request", request);
  refresh(node);
  try {
    const snapshot = await app.graphToPrompt();
    if (task.cancelRequested) return;
    const graph = pruneToUpstream(snapshot, String(node.id));
    const result = await api.queuePrompt(0, graph, {
      partialExecutionTargets: [String(node.id)],
    });
    if (!result?.prompt_id) throw new Error(result?.error?.message || "ComfyUI rejected the partial execution");
    task.jobId = String(result.prompt_id);
    if (task.cancelRequested) await cancelManual(node);
  } catch (error) {
    pending.delete(request);
    node._ellmPending = null;
    notify("error", "Enhancement queue failed: " + error.message);
  } finally {
    // The queue owns its immutable serialized request. The visible workflow
    // must never remain armed or run a manual batch on the next normal queue.
    setValue(node, "manual_request", "");
    refresh(node);
  }
}

function refresh(node) {
  const panel = node?._ellmPanel;
  if (!panel) return;
  const list = history(node);
  const active = index(node);
  panel.count.textContent = list.length ? (active + 1) + " / " + list.length : "0 / 0";
  panel.run.textContent = node._ellmPending ? "Cancel Enhancement" : "Enhance Prompt";
  panel.run.title = node._ellmPending ? "Cancel this queued/running partial execution" :
    "Queue only the enhancer and its upstream model/media dependencies";
  panel.undo.disabled = !(node._ellmUndo?.length);
  panel.redo.disabled = !(node._ellmRedo?.length);
  panel.prev.disabled = panel.next.disabled = panel.remove.disabled = !list.length;
  panel.promote.disabled = !String(value(node, "enhanced_prompt")).trim();
  if (node._ellmPending) panel.status.textContent = "Queued / generating " +
    value(node, "batch_count", 1) + " prompt(s)…";
}

function makeElement(tag, label, parent, click, cssClass = "") {
  const element = document.createElement(tag);
  if (label != null) element.textContent = label;
  if (cssClass) element.className = cssClass;
  if (click) element.addEventListener("click", click);
  parent.append(element);
  return element;
}
function panelButton(row, label, callback) {
  const button = makeElement("button", label, row, event => {
    event.preventDefault();
    event.stopPropagation();
    void callback();
  });
  button.type = "button";
  return button;
}
function buildPanel(node) {
  if (node._ellmPanel) return;
  const root = document.createElement("div");
  root.className = "ellm-enhancer-panel";
  const rowA = makeElement("div", null, root, null, "ellm-row");
  const run = panelButton(rowA, "Enhance Prompt", () => runManual(node));
  run.classList.add("ellm-primary");
  const promote = panelButton(rowA, "↑ Use Enhanced as Prompt", () => useEnhancedAsPrompt(node));
  const rowB = makeElement("div", null, root, null, "ellm-row");
  const prev = panelButton(rowB, "←", () => choose(node, index(node) - 1));
  const count = makeElement("span", "0 / 0", rowB, null, "ellm-counter");
  const next = panelButton(rowB, "→", () => choose(node, index(node) + 1));
  const remove = panelButton(rowB, "Delete", () => deleteActive(node));
  const undoBtn = panelButton(rowB, "Undo", () => undo(node));
  const redoBtn = panelButton(rowB, "Redo", () => undo(node, true));
  panelButton(rowB, "Clear", () => clearAll(node));
  const rowC = makeElement("div", null, root, null, "ellm-row");
  makeElement("span", "Template", rowC, null, "ellm-label");
  const template = makeElement("select", null, rowC);
  template.addEventListener("change", () => selectTemplate(node, template.value));
  panelButton(rowC, "Save", () => saveTemplate(node));
  panelButton(rowC, "Delete", () => deleteTemplate(node));
  const rowD = makeElement("div", null, root, null, "ellm-row");
  makeElement("span", "Prompt Set", rowD, null, "ellm-label");
  const set = makeElement("select", null, rowD);
  panelButton(rowD, "Save", () => saveSet(node));
  panelButton(rowD, "Load", () => loadSet(node));
  panelButton(rowD, "Delete", () => deleteSet(node));
  const status = makeElement("div", "Ready", root, null, "ellm-status");
  node._ellmPanel = {
    root, run, count, promote, prev, next, remove, undo: undoBtn, redo: redoBtn,
    template, set, status,
  };
  if (typeof node.addDOMWidget === "function") {
    const widget = node.addDOMWidget("enhancer_controls", "enhancer_controls", root, {
      serialize: false, hideOnZoom: false, margin: 4,
      getValue: () => "", setValue: () => {},
      getMinHeight: () => 214, getHeight: () => 214,
    });
    widget.serialize = false;
    widget.options ??= {};
    widget.options.serialize = false;
    node.size[0] = Math.max(node.size[0], 470);
  } else {
    // Older frontends still offer the manual and history actions.
    node.addWidget("button", "Enhance Prompt", null, () => runManual(node));
    node.addWidget("button", "Previous Enhanced Prompt", null, () => choose(node, index(node) - 1));
    node.addWidget("button", "Next Enhanced Prompt", null, () => choose(node, index(node) + 1));
  }
  refresh(node);
}

function hideInternalWidget(node, name) {
  const widget = w(node, name);
  if (!widget || widget._ellmHidden) return;
  widget._ellmHidden = true;
  widget.hidden = true;
  widget.options ??= {};
  widget.options.hidden = true;
  widget.computeSize = () => [0, 0];
  widget.computeLayoutSize = () => ({ minHeight: 0, maxHeight: 0, minWidth: 0 });
  // Do not set widget.serialize=false. Workflow JSON and API prompt must
  // continue to own and serialize these values across graph reconfiguration.
}

function ensureStateId(node) {
  let id = String(value(node, "state_id", "")).trim();
  if (!id || (node.graph?._nodes ?? []).some(n => n !== node && String(value(n, "state_id")) === id)) {
    id = freshId();
    setValue(node, "state_id", id);
  }
  return id;
}

function wrapVisibleEdit(node) {
  const widget = w(node, "enhanced_prompt");
  if (!widget || widget._ellmWatched) return;
  widget._ellmWatched = true;
  const original = widget.callback;
  widget.callback = function (text, ...args) {
    const returned = original?.call(this, text, ...args);
    if (!node._ellmSyncing) {
      rememberUndo(node);
      const list = history(node);
      const at = index(node);
      const fresh = String(text ?? "");
      if (!list.length) list.push(fresh);
      else list[at] = fresh;
      writeHistory(node, list, at);
      setValue(node, "cycle_counter", 0);
    }
    return returned;
  };
}

function installCycleListeners(node) {
  for (const key of ["prompt_cycle", "enhance_with_workflow"]) {
    const widget = w(node, key);
    if (!widget || widget._ellmWatched) continue;
    widget._ellmWatched = true;
    const original = widget.callback;
    widget.callback = function (next, ...args) {
      const returned = original?.call(this, next, ...args);
      setValue(node, "cycle_counter", 0);
      syncCycleControl(node);
      return returned;
    };
  }
  syncCycleControl(node);
}

function mount(node) {
  if (!node || node._ellmMounted) return;
  node._ellmMounted = true;
  ensureStateId(node);
  installCycleListeners(node);
  wrapVisibleEdit(node);
  buildPanel(node);
  if (typeof node.addDOMWidget === "function") {
    for (const name of ["history_json", "active_index", "manual_request",
      "state_id", "enhancement_preset", "cycle_counter"]) {
      hideInternalWidget(node, name);
    }
    const counterControl = w(node, "cycle_counter")?.linkedWidgets || [];
    for (const linked of counterControl) {
      linked.hidden = true;
      linked.computeSize = () => [0, 0];
    }
  }
  void refreshTemplates(node);
  void refreshSets(node);
  replay(node);
  refresh(node);
}

function handleFailed(e) {
  const detail = e?.detail ?? e;
  const id = String(detail?.prompt_id || "");
  if (!id) return;
  for (const task of pending.values()) {
    if (task.jobId !== id) continue;
    pending.delete(task.request);
    task.node._ellmPending = null;
    setValue(task.node, "manual_request", "");
    refresh(task.node);
    notify("error", detail?.exception_message || "Enhancement execution failed or was interrupted");
  }
}

function injectStyles() {
  if (document.getElementById("ellm-enhancer-css")) return;
  const style = document.createElement("style");
  style.id = "ellm-enhancer-css";
  style.textContent = [
    ".ellm-enhancer-panel{width:100%;height:214px;box-sizing:border-box;overflow:auto;",
    "padding:8px;display:flex;flex-direction:column;gap:7px;",
    "font:12px system-ui;color:var(--fg-color,#ddd);background:var(--comfy-input-bg,#23232b);border-radius:7px}",
    ".ellm-row{display:flex;align-items:center;gap:5px;min-height:31px;flex-wrap:wrap}",
    ".ellm-row button,.ellm-row select{font:inherit;color:inherit;background:var(--bg-color,#363640);",
    "border:1px solid var(--border-color,#555);border-radius:5px;padding:5px 7px;cursor:pointer}",
    ".ellm-row button:hover{filter:brightness(1.13)}.ellm-row button:disabled{opacity:.45;cursor:default}",
    ".ellm-row .ellm-primary{background:var(--p-button-primary-background,#405f91);font-weight:600}",
    ".ellm-row select{min-width:130px;max-width:210px;flex:1}",
    ".ellm-label{min-width:65px;font-weight:600}.ellm-counter{min-width:42px;text-align:center}",
    ".ellm-status{opacity:.75;font-size:11px;min-height:18px}",
  ].join("");
  document.head.append(style);
}

app.registerExtension({
  name: "EnhancedLLM.PromptEnhancer",
  setup() {
    injectStyles();
    api.addEventListener?.("executed", onGenerated);
    api.addEventListener?.("execution_error", handleFailed);
    api.addEventListener?.("execution_interrupted", handleFailed);
  },
  nodeCreated(node) {
    if (node?.comfyClass === NODE_TYPE) setTimeout(() => mount(node), 0);
  },
  loadedGraphNode(node) {
    if (node?.comfyClass === NODE_TYPE) setTimeout(() => mount(node), 0);
  },
  afterConfigureGraph() {
    for (const node of app.graph?._nodes ?? []) {
      if (node?.comfyClass === NODE_TYPE) {
        if (!node._ellmMounted) mount(node);
        replay(node);
      }
    }
  },
});
