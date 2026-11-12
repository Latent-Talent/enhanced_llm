import test from "node:test";
import assert from "node:assert/strict";
import { parseHistory, clampIndex, appendResults, removeAt, selectedPrompt, pruneToUpstream } from "../../web/js/enhancer_state.mjs";

test("history state JSON parsing and navigation", () => {
  assert.deepEqual(parseHistory('["a","b"]'), ["a", "b"]);
  assert.deepEqual(parseHistory("invalid"), []);
  assert.equal(clampIndex(-9, 3), 0);
  assert.equal(clampIndex(99, 3), 2);
  assert.equal(selectedPrompt(["", "hello"], 1, "original"), "hello");
  assert.equal(selectedPrompt([], 1, "original"), "original");
});

test("append, overwrite and delete prompt history", () => {
  assert.deepEqual(appendResults(["x"], 0, ["new"], true), { prompts: ["new"], index: 0 });
  assert.deepEqual(appendResults(["x"], 0, ["one", "two"], true), {
    prompts: ["x", "one", "two"], index: 2
  });
  assert.deepEqual(removeAt(["a", "b", "c"], 1), { prompts: ["a", "c"], index: 1 });
});

test("manual partial execution excludes unrelated downstream branches", () => {
  const data = { output: {
    "1": { inputs: { raw: "text" } },
    "2": { inputs: { llm: ["1", 0] } },
    "3": { inputs: { llm: ["2", 0], image: ["4", 0] } },
    "4": { inputs: {} },
    "5": { inputs: { enhanced: ["3", 0] } },
    "6": { inputs: { unrelated: true } },
  }, workflow: { state: 12 } };
  const result = pruneToUpstream(data, "3");
  assert.deepEqual(Object.keys(result.output), ["1", "2", "3", "4"]);
  assert.deepEqual(result.workflow, { state: 12 });
  assert.equal(data.output["5"].inputs.enhanced[0], "3");
});
