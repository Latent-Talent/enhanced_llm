import test from "node:test";
import assert from "node:assert/strict";
import { summarizeBatch, buttonLabel } from "../../web/progress.mjs";

test("progress labels live in the enhance button, including cancel state",()=>{
  assert.equal(buttonLabel(), "Enhance");
  assert.equal(buttonLabel(0,5,true), "Cancel · 0/5");
  assert.equal(buttonLabel(3,5,true), "Cancel · 3/5");
  assert.equal(buttonLabel(5,5,false), "Enhance");
  assert.equal(buttonLabel(7,5,false), "Enhance");
  assert.equal(buttonLabel(1,5,false), "Enhance"); // after cancellation
  assert.equal(buttonLabel(0,0,false), "Enhance"); // after a failed submission
});

test("only successful enhancements advance progress",()=>{
  const jobs=[
    {state:"full_queued"},{state:"enhanced"},{state:"pending"},
    {state:"error"},{state:"cancelled"},{state:"full_error"}
  ];
  assert.deepEqual(summarizeBatch(jobs),{
    completed:3,total:5,cancelled:1,active:1,terminal:false,failed:1,fullRunErrors:1
  });
  assert.deepEqual(summarizeBatch(jobs.filter(j=>j.state!=="pending")),{
    completed:3,total:4,cancelled:1,active:0,terminal:true,failed:1,fullRunErrors:1
  });
  assert.deepEqual(summarizeBatch([]),{
    completed:0,total:0,cancelled:0,active:0,terminal:false,failed:0,fullRunErrors:0
  });
});


test("native queue cancellation shrinks denominator without losing successes",()=>{
  const jobs=[
    {state:"enhanced"},{state:"pending"},{state:"cancelled"},
    {state:"pending"},{state:"pending"}
  ];
  const progress=summarizeBatch(jobs);
  assert.equal(buttonLabel(progress.completed,progress.total,progress.active>0),"Cancel · 1/4");
  const updated=summarizeBatch([
    {state:"enhanced"},{state:"cancelled"},{state:"cancelled"},
    {state:"enhanced"},{state:"pending"}
  ]);
  assert.equal(buttonLabel(updated.completed,updated.total,updated.active>0),"Cancel · 2/3");
});

test("button becomes Enhance when every enhancement is cancelled",()=>{
  const cancelled=summarizeBatch([
    {state:"cancelled"},{state:"cancelled"},{state:"cancelled"}
  ]);
  assert.equal(cancelled.cancelled,3);
  assert.equal(cancelled.total,0);
  assert.equal(cancelled.active,0);
  assert.equal(cancelled.terminal,true);
  assert.equal(buttonLabel(cancelled.completed,cancelled.total,cancelled.active>0),"Enhance");
});

test("successful jobs remain counted when all remaining jobs are cancelled",()=>{
  const progress=summarizeBatch([
    {state:"full_queued"},{state:"enhanced"},{state:"cancelled"},{state:"cancelled"}
  ]);
  assert.equal(progress.completed,2);
  assert.equal(progress.total,2);
  assert.equal(progress.active,0);
  assert.equal(progress.terminal,true);
  assert.equal(buttonLabel(progress.completed,progress.total,progress.active>0),"Enhance");
});
