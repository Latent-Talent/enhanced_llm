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

test("enhancement progress is in the button and the permanent footer is removed",()=>{
  assert.match(ui, /buttonLabel\(done,total,running\)/);
  assert.match(ui, /summarizeBatch\(data\.jobs\)/);
  assert.ok(ui.includes('"/enhanced_llm/batch/"+encodeURIComponent(id)+"/cancel"'));
  assert.doesNotMatch(ui, /full runs queued /);
  assert.match(ui, /data-eml="status" role="alert" aria-live="polite" hidden/);
  assert.match(css, /\.eml-status\[hidden\] \{ display: none !important; \}/);
});
test("optional jailbreak textarea is workflow-backed and collapsible",()=>{
  assert.match(ui, /Jailbreak \(optional\)/);
  assert.match(ui, /data-eml="jailbreak" rows="3"/);
  assert.match(ui, /set\(node,"jailbreak_text",at\("jailbreak"\)\.value\)/);
  assert.match(ui, /at\("jailbreak"\)\.value=String\(get\(node,"jailbreak_text"\)\|\|""\)/);
  assert.match(ui, /resize\.setJailbreakVisible\(open\)/);
  assert.match(css, /\.eml-jailbreak summary/);
});

test("enhancement batching uses ComfyUI lifecycle hooks for upstream seed nodes",()=>{
  assert.match(ui, /app\.queuePrompt\(0,count,\{queueNodeIds:\[String\(node\.id\)\]\}\)/);
  assert.match(ui, /dom\.beforeQueued=\(\{isPartialExecution\}=\{\}\)=>/);
  assert.match(ui, /dom\.afterQueued=\(\{isPartialExecution\}=\{\}\)=>/);
  assert.match(ui, /submittingBatch\.submitted\.push\(submittingBatch\.current\)/);
  assert.match(ui, /if\(!isPartialExecution\)advanceCycle\(\)/);
  assert.match(ui, /enhanced_llm\/batch\/reserve/);
  assert.match(ui, /submitted_job_ids:submitted/);
  assert.doesNotMatch(ui, /enhanced_llm\/queue/);
});
