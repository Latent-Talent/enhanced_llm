import test from "node:test";
import assert from "node:assert/strict";
import { summarizeBatch, buttonLabel } from "../../web/progress.mjs";

test("progress labels live in the enhance button, including cancel state",()=>{
  assert.equal(buttonLabel(), "Enhance Prompt");
  assert.equal(buttonLabel(0,5,true), "Cancel · 0/5");
  assert.equal(buttonLabel(3,5,true), "Cancel · 3/5");
  assert.equal(buttonLabel(5,5,false), "Enhance Prompt · 5/5");
  assert.equal(buttonLabel(7,5,false), "Enhance Prompt · 5/5");
});

test("only successful enhancements advance progress",()=>{
  const jobs=[
    {state:"full_queued"},{state:"enhanced"},{state:"pending"},
    {state:"error"},{state:"cancelled"},{state:"full_error"}
  ];
  assert.deepEqual(summarizeBatch(jobs),{
    completed:3,total:6,terminal:false,failed:1,fullRunErrors:1
  });
  assert.deepEqual(summarizeBatch(jobs.filter(j=>j.state!=="pending")),{
    completed:3,total:5,terminal:true,failed:1,fullRunErrors:1
  });
  assert.deepEqual(summarizeBatch([]),{
    completed:0,total:0,terminal:false,failed:0,fullRunErrors:0
  });
});
