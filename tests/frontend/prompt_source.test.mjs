import test from "node:test";
import assert from "node:assert/strict";
import {promptInputSlots,promptInputSlot,usesPromptInput,canEnhancePrompt} from "../../web/prompt_source.mjs";

const node=(link=null)=>({
  inputs:[{name:"clip",link:1},{name:"audio1",link:null},
          {name:"prompt_input",link},{name:"prompt",link:null}]
});

test("dedicated native prompt socket is found below audio",()=>{
  assert.deepEqual(promptInputSlot(node(0)),{index:2,connected:true});
  assert.equal(usesPromptInput(node(0)),true);
  assert.deepEqual(promptInputSlots(node(0)),[
    {index:2,connected:true},{index:3,connected:false},
  ]);
});

test("a connected STRING source hides the editable field and enables enhancement",()=>{
  assert.equal(canEnhancePrompt(node(2),""),true);
  assert.equal(canEnhancePrompt(node(2),"stale widget text"),true);
  assert.equal(usesPromptInput(node(null)),false);
  assert.equal(canEnhancePrompt(node(null),"typed text"),true);
  assert.equal(canEnhancePrompt(node(null),"  "),false);
});

test("legacy widget-backed prompt connections continue to work",()=>{
  const legacy={inputs:[{name:"clip",link:1},{name:"prompt",link:5}]};
  assert.equal(usesPromptInput(legacy),true);
  assert.equal(canEnhancePrompt(legacy,""),true);
  assert.deepEqual(promptInputSlot(legacy),{index:1,connected:true});
});

test("input mode does not depend on stored UI properties",()=>{
  const graph=node(null);
  graph.properties={enhancedLLMUsePromptInput:true};
  assert.equal(usesPromptInput(graph),false);
  assert.deepEqual(promptInputSlot({inputs:[]}),{index:-1,connected:false});
});
