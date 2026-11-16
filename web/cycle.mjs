// Pure, deterministic selectors; no Math.random in either random mode.
export const MODES = Object.freeze(["fixed", "increment", "decrement", "shuffle", "random"]);

export function hash32(seed, index) {
  let x = ((Number(seed) >>> 0) ^ Math.imul((Number(index) + 1) >>> 0, 0x9e3779b9)) >>> 0;
  x ^= x >>> 16; x = Math.imul(x, 0x7feb352d);
  x ^= x >>> 15; x = Math.imul(x, 0x846ca68b);
  return (x ^ (x >>> 16)) >>> 0;
}

export function shuffledIndices(length, seed) {
  const items = Array.from({length}, (_, i) => i);
  for (let i = items.length - 1; i > 0; i--) {
    const j = hash32(seed, i) % (i + 1);
    [items[i], items[j]] = [items[j], items[i]];
  }
  return items;
}

export function nextIndex(mode, index, length, seed, step) {
  if (!Number.isInteger(length) || length <= 0) return -1;
  const current = Number.isInteger(index) && index >= 0 ? index % length : 0;
  const n = Math.max(0, Math.floor(Number(step) || 0));
  if (mode === "fixed") return current;
  if (mode === "increment") return (current + 1) % length;
  if (mode === "decrement") return (current + length - 1) % length;
  if (mode === "random") return hash32(seed, n) % length;
  if (mode === "shuffle") {
    const round = Math.floor(n / length);
    return shuffledIndices(length, hash32(seed, round))[n % length];
  }
  return current;
}
