/* Pure enhancer UI state transformations. No DOM or ComfyUI dependencies. */

export function parseHistory(input) {
  try {
    const value = Array.isArray(input) ? input : JSON.parse(String(input || "[]"));
    if (!Array.isArray(value) || value.length > 512 || value.some(x => typeof x !== "string")) return [];
    return value;
  } catch {
    return [];
  }
}

export function clampIndex(index, count) {
  if (!count) return 0;
  const n = Number(index);
  return Math.max(0, Math.min(count - 1, Number.isFinite(n) ? Math.trunc(n) : 0));
}

export function appendResults(history, index, results, overwrite = false) {
  const copy = parseHistory(history);
  const clean = Array.isArray(results) ? results.filter(x => typeof x === "string" && x.trim()) : [];
  if (!clean.length) return { prompts: copy, index: clampIndex(index, copy.length) };
  if (overwrite && clean.length === 1 && copy.length) {
    const position = clampIndex(index, copy.length);
    copy[position] = clean[0];
    return { prompts: copy, index: position };
  }
  copy.push(...clean);
  if (copy.length > 512) copy.splice(0, copy.length - 512);
  return { prompts: copy, index: copy.length - 1 };
}

export function removeAt(history, index) {
  const copy = parseHistory(history);
  if (!copy.length) return { prompts: copy, index: 0 };
  copy.splice(clampIndex(index, copy.length), 1);
  return { prompts: copy, index: clampIndex(index, copy.length) };
}

export function selectedPrompt(history, index, original = "") {
  const list = parseHistory(history);
  return (list[clampIndex(index, list.length)] || "").trim() || original;
}

export function pruneToUpstream(promptData, targetId) {
  const output = promptData?.output;
  const id = String(targetId ?? "");
  if (!output || typeof output !== "object" || !Object.hasOwn(output, id)) {
    throw new Error("The Prompt Enhancer node is missing from the serialized ComfyUI graph.");
  }
  const kept = new Set();

  const visit = nodeId => {
    const key = String(nodeId);
    if (kept.has(key) || !Object.hasOwn(output, key)) return;
    kept.add(key);
    for (const value of Object.values(output[key]?.inputs || {})) inspect(value);
  };

  const inspect = value => {
    if (Array.isArray(value)) {
      if (value.length === 2 && Object.hasOwn(output, String(value[0])) &&
          Number.isInteger(value[1])) {
        visit(value[0]);
        return;
      }
      for (const child of value) inspect(child);
    } else if (value && typeof value === "object") {
      for (const child of Object.values(value)) inspect(child);
    }
  };
  visit(id);
  return {
    ...promptData,
    output: Object.fromEntries(Object.entries(output).filter(([key]) => kept.has(key))),
  };
}
