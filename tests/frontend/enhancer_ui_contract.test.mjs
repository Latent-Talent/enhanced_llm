import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../../web/js/prompt_enhancer.js", import.meta.url), "utf8");

test("prominent Enhance action and matching cancel state", () => {
  assert.match(source, /panelButton\(rowA, "Enhance", \(\) => runManual\(node\)\)/);
  assert.match(source, /busy \? "Cancel" : "Enhance"/);
  assert.match(source, /node\.addWidget\("button", "Enhance"/);
});

test("modern ComfyUI theme tokens and accessible controls", () => {
  for (const token of ["--foreground", "--background", "--secondary", "--node",
                       "--primary", "--muted-foreground", "--border"]) {
    assert.ok(source.includes(token), token);
  }
  assert.doesNotMatch(source, /--p-(primary|surface|text)/);
  assert.match(source, /aria-live/);
  assert.match(source, /focus-visible/);
});

test("native inference and partial queue still connected to Enhance", () => {
  assert.match(source, /function runManual\(node\)/);
  assert.match(source, /pruneToUpstream\(snapshot, String\(node.id\)\)/);
  assert.match(source, /api\.queuePrompt\(0, graph/);
  assert.match(source, /function addGenerated\(node, response\)/);
});
