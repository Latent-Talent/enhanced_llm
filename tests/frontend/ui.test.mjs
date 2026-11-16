import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const ui=readFileSync(new URL("../../web/main.js",import.meta.url),"utf8");
const css=readFileSync(new URL("../../web/styles.css",import.meta.url),"utf8");

test("queue switch is in the UI, not hidden behind native widgets",()=>{
  assert.match(ui, /Queue Run for Each/);
  assert.match(ui, /data-eml="run-each" type="checkbox" role="switch"/);
  assert.match(ui, /at\("run-each"\)\.checked=Boolean\(get\(node,"queue_run_for_each"\)\)/);
  assert.match(css, /\.eml-toggle-control/);
  assert.match(css, /input:checked \+ \.eml-switch-track/);
});
test("cycle uses an automatic random seed rather than a visible seed input",()=>{
  assert.doesNotMatch(ui, /data-eml="cycle-seed"/);
  assert.match(ui, /function automaticSeed\(/);
  assert.match(ui, /automaticSeed\(\)/);
  assert.match(ui, /set\.shuffleSeed=automaticSeed\(\)/);
  assert.match(ui, /nextIndex\("random",state\.index,n,automaticSeed\(\),0\)/);
});
test("resizing a textarea drives its node's layout, and is cleaned up",()=>{
  assert.match(ui, /createTextareaResizeController\(node\)/);
  assert.match(ui, /new ResizeObserver\(entries/);
  assert.match(ui, /resize\.observedHeight\(key,entry\.target\.offsetHeight\)/);
  assert.match(ui, /getMinHeight:\(\)=>resize\.minHeight\(\)/);
  assert.match(ui, /textareaObserver\?\.disconnect\(\)/);
  assert.match(css, /resize:\s*vertical/);
});
test("buttons are scoped, evenly sized, and content does not shrink",()=>{
  assert.match(css, /\.eml-row button \{/);
  assert.match(css, /min-height:\s*30px/);
  assert.match(css, /\.eml-panel > \* \{\s*flex-shrink: 0/);
});
