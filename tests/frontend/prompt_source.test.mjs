import test from "node:test";
import assert from "node:assert/strict";
import {promptInputSlot,usesPromptInput,canEnhancePrompt} from "../../web/prompt_source.mjs";

const node=(link=null,inputMode=false)=>({
  inputs:[{name:"clip",link:1},{name:"prompt",link}],
  properties:{enhancedLLMUsePromptInput:inputMode},
});

test("native widget-backed prompt socket is recognized and accepts link id zero",()=>{
  assert.deepEqual(promptInputSlot(node(0)),{index:1,connected:true});
  assert.deepEqual(promptInputSlot(node(null)),{index:1,connected:false});
  assert.deepEqual(promptInputSlot({inputs:[{name:"other",widget:{name:"prompt"},link:5}]}),
    {index:0,connected:true});
});

test("input overrides stored text; no empty-prompt rejection when connected",()=>{
  assert.equal(usesPromptInput(node(2)),true);
  assert.equal(canEnhancePrompt(node(2),""),true);
  assert.equal(canEnhancePrompt(node(2),"stale local text"),true);
});

test("text fallback and explicit input mode without a connection",()=>{
  assert.equal(usesPromptInput(node(null)),false);
  assert.equal(canEnhancePrompt(node(null),"local prompt"),true);
  assert.equal(canEnhancePrompt(node(null),"  "),false);
  assert.equal(usesPromptInput(node(null,true)),true);
  assert.equal(canEnhancePrompt(node(null,true),"stale text"),false);
});

test("no socket does not throw",()=>{
  assert.deepEqual(promptInputSlot({inputs:[]}),{index:-1,connected:false});
  assert.equal(canEnhancePrompt({inputs:[]},"typed text"),true);
});
