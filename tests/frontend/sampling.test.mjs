import test from "node:test";
import assert from "node:assert/strict";
import {SAMPLING_PRESETS,applySamplingPreset,matchingSamplingPreset} from "../../web/sampling.mjs";

function nativeNode({mode="on"}={}){
  const events=[];
  const widgets=[
    {name:"sampling_mode",value:mode,callback:val=>events.push(["sampling_mode",val])},
    {name:"max_length",value:1024,callback:val=>events.push(["max_length",val])},
    ...["temperature","top_k","top_p","min_p","repetition_penalty","presence_penalty","seed"]
      .map(name=>({name:"sampling_mode."+name,value:name==="seed"?123:0,
        callback:val=>events.push([name,val])})),
    {name:"thinking",value:false},
    {name:"use_default_template",value:true},
    {name:"mtp",value:"auto"}
  ];
  const node={widgets,inputs:[],events,setDirtyCanvas(...args){this.dirty=args;}};
  return node;
}

test("presets are descriptive, valid for native ComfyUI V2, and do not contain a seed",()=>{
  assert.equal(SAMPLING_PRESETS.length,5);
  assert.equal(new Set(SAMPLING_PRESETS.map(x=>x.id)).size,5);
  for(const p of SAMPLING_PRESETS){
    assert.ok(p.name.length>7);
    assert.ok(p.description.length>45);
    assert.equal(Object.hasOwn(p.values,"seed"),false);
    assert.ok(p.values.temperature>=0.01 && p.values.temperature<=2);
    assert.ok(p.values.top_k>=0&&p.values.top_k<=1000);
    assert.ok(p.values.top_p>=0&&p.values.top_p<=1);
    assert.ok(p.values.min_p>=0&&p.values.min_p<=1);
    assert.ok(p.values.repetition_penalty>=0&&p.values.repetition_penalty<=5);
    assert.ok(p.values.presence_penalty>=0&&p.values.presence_penalty<=5);
    assert.ok(p.values.max_length>=1&&p.values.max_length<=32768);
  }
});

test("balanced preset writes real dynamic combo children, preserving seed and MTP",()=>{
  const node=nativeNode();
  const r=applySamplingPreset(node,"balanced");
  assert.equal(r.preset.id,"balanced");
  assert.equal(r.matched,true);
  assert.equal(node.widgets.find(w=>w.name==="max_length").value,1024);
  assert.equal(node.widgets.find(w=>w.name==="sampling_mode.temperature").value,0.70);
  assert.equal(node.widgets.find(w=>w.name==="sampling_mode.top_p").value,0.92);
  assert.equal(node.widgets.find(w=>w.name==="sampling_mode.seed").value,123);
  assert.equal(node.widgets.find(w=>w.name==="mtp").value,"auto");
  assert.equal(node.widgets.find(w=>w.name==="thinking").value,false);
  assert.equal(node.widgets.find(w=>w.name==="use_default_template").value,true);
  assert.equal(node.widgets.find(w=>w.name==="sampling_mode").value,"on");
  assert.equal(matchingSamplingPreset(node)?.id,"balanced");
  assert.deepEqual(node.dirty,[true,true]);
  assert.ok(node.events.some(([name,value])=>name==="temperature"&&value===0.70));
});

test("linked controls stay owned by their upstream source",()=>{
  const node=nativeNode();
  node.inputs=[{name:"sampling_mode.temperature",link:7},{name:"sampling_mode.seed",link:9}];
  const r=applySamplingPreset(node,"creative");
  assert.deepEqual(r.skipped,["temperature"]);
  assert.equal(node.widgets.find(w=>w.name==="sampling_mode.temperature").value,0);
  assert.equal(node.widgets.find(w=>w.name==="sampling_mode.seed").value,123);
  assert.equal(r.matched,false);
});

test("manual edits are detected as custom instead of retaining an inaccurate label",()=>{
  const node=nativeNode();
  applySamplingPreset(node,"faithful");
  assert.equal(matchingSamplingPreset(node)?.id,"faithful");
  node.widgets.find(w=>w.name==="sampling_mode.top_k").value=90;
  assert.equal(matchingSamplingPreset(node),null);
});

test("applying a preset turns native Sampling Mode on, without seed modification",()=>{
  const node=nativeNode({mode:"off"});
  const before=node.widgets.find(w=>w.name==="sampling_mode.seed").value;
  const r=applySamplingPreset(node,"structured");
  assert.equal(node.widgets.find(w=>w.name==="sampling_mode").value,"on");
  assert.equal(node.widgets.find(w=>w.name==="max_length").value,2048);
  assert.equal(node.widgets.find(w=>w.name==="sampling_mode.seed").value,before);
  assert.equal(r.preset.id,"structured");
  assert.ok(node.events.some(([name,value])=>name==="sampling_mode"&&value==="on"));
});

test("missing native widgets report an error and never create a second seed control",()=>{
  const node=nativeNode();
  node.widgets=node.widgets.filter(w=>w.name!=="sampling_mode.min_p");
  assert.throws(()=>applySamplingPreset(node,"balanced"),/Native sampling widgets not found: min_p/);
  assert.throws(()=>applySamplingPreset(node,"not-real"),/Unknown LLM sampling preset/);
});
