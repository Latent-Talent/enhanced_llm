// Keep the DOM widget and its LiteGraph node in sync when a textarea's
// native resize grip is dragged. No polling, no dependency on canvas zoom.
export const TEXTAREA_HEIGHTS = Object.freeze({
  prompt: 96,
  enhanced: 116,
  instructions: 116,
  jailbreak: 88,
});
export const BASE_PANEL_HEIGHT = 640;
export const HEIGHT_PROPERTY = "enhancedLLMTextHeights";

function normalizeHeight(value, fallback) {
  const size = Number(value);
  return Number.isFinite(size) && size >= 62 && size <= 3000
    ? Math.round(size * 10) / 10
    : fallback;
}

export function createTextareaResizeController(node) {
  const sizes = {...TEXTAREA_HEIGHTS};
  const observed = new Set();
  let jailbreakVisible = false;

  function restore(saved, showJailbreak = false) {
    observed.clear();
    jailbreakVisible = !!showJailbreak;
    for (const [key, fallback] of Object.entries(TEXTAREA_HEIGHTS)) {
      sizes[key] = normalizeHeight(saved?.[key], fallback);
    }
  }

  function minHeight() {
    const additional = Object.entries(TEXTAREA_HEIGHTS).reduce(
      (total, [key, baseline]) => total +
        (key === "jailbreak" ? (jailbreakVisible ? sizes[key] + 8 : 0) : sizes[key] - baseline),
      0
    );
    return Math.max(460, Math.ceil(BASE_PANEL_HEIGHT + additional));
  }

  function setJailbreakVisible(visible) {
    visible = !!visible;
    if (jailbreakVisible === visible) return false;
    const previous = minHeight();
    jailbreakVisible = visible;
    observed.delete("jailbreak"); // fresh DOM measurement when reopened
    const delta = minHeight() - previous;
    const width = Number(node.size?.[0]) || 565;
    const height = Number(node.size?.[1]) || 880;
    const required = Number(node.computeSize?.()?.[1]) || 0;
    node.setSize?.([width, Math.max(required, height + delta)]);
    node.setDirtyCanvas?.(true, true);
    return true;
  }

  function observedHeight(key, height) {
    if (!(key in TEXTAREA_HEIGHTS) || (key === "jailbreak" && !jailbreakVisible)) return false;
    const next = normalizeHeight(height, sizes[key]);
    const previous = sizes[key];
    sizes[key] = next;

    // Browser mount, workflow loading and restoring node dimensions are
    // baseline measurements, not user resize operations.
    if (!observed.has(key)) {
      observed.add(key);
      return false;
    }
    const delta = next - previous;
    if (Math.abs(delta) < 0.5) return false;

    // LiteGraph serializes node.properties in workflow JSON. The textarea
    // dimensions must survive reloads independently of the node bounding box.
    if (!node.properties) node.properties = {};
    node.properties[HEIGHT_PROPERTY] = {...sizes};

    // Preserve any extra height the user gave the node with its own resize
    // handle. Only apply the textarea's incremental change.
    const width = Number(node.size?.[0]) || 565;
    const before = Number(node.size?.[1]) || 880;
    const required = Number(node.computeSize?.()?.[1]) || 0;
    const nextNodeHeight = Math.max(required, before + delta);
    if (Number.isFinite(nextNodeHeight) && Math.abs(nextNodeHeight - before) >= 0.5) {
      node.setSize?.([width, nextNodeHeight]);
    }
    node.setDirtyCanvas?.(true, true);
    return true;
  }

  return {
    restore,
    minHeight,
    observedHeight,
    setJailbreakVisible,
    size: key => sizes[key],
  };
}
