// Small pure functions for rendering enhancement progress inside the action button.
// A completed enhancement can queue a full workflow; queued full runs are not
// counted as additional enhancements.
const SUCCESS = new Set(["enhanced", "full_queued", "full_error"]);
const TERMINAL = new Set([...SUCCESS, "cancelled", "error"]);

export function summarizeBatch(jobs) {
  const list = Array.isArray(jobs) ? jobs : [];
  return {
    completed: list.filter(j => SUCCESS.has(j?.state)).length,
    total: list.length,
    terminal: list.length > 0 && list.every(j => TERMINAL.has(j?.state)),
    failed: list.filter(j => j?.state === "error").length,
    fullRunErrors: list.filter(j => j?.state === "full_error").length,
  };
}

export function buttonLabel(completed = 0, total = 0, active = false) {
  if (!active) return "Enhance";
  const label = "Cancel";
  if (!total) return label;
  const n = Math.max(0, Math.min(total, Math.floor(Number(completed) || 0)));
  return label + " · " + n + "/" + total;
}
