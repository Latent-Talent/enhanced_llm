import test from "node:test";
import assert from "node:assert/strict";
import {hash32, shuffledIndices, nextIndex} from "../../web/cycle.mjs";
import {DEFAULT_PRESETS,isDefaultPreset,getPreset,validateUserPresets} from "../../web/presets.mjs";

test("seeded random is repeatable and never out of range",()=>{
  const a=Array.from({length:200},(_,i)=>nextIndex("random",0,7,123,i));
  assert.deepEqual(a,Array.from({length:200},(_,i)=>nextIndex("random",0,7,123,i)));
  assert.ok(a.every(x=>x>=0&&x<7));assert.ok(new Set(a).size>1);
});
test("shuffle visits every index before repeating",()=>{
  for(let n=1;n<=12;n++){
    const a=shuffledIndices(n,123);
    assert.deepEqual([...a].sort((x,y)=>x-y),Array.from({length:n},(_,i)=>i));
    const cycle=Array.from({length:n},(_,i)=>nextIndex("shuffle",0,n,123,i));
    assert.deepEqual([...cycle].sort((x,y)=>x-y),Array.from({length:n},(_,i)=>i));
  }
});
test("fixed increment decrement and empty",()=>{
  assert.equal(nextIndex("fixed",2,5,0,0),2);
  assert.equal(nextIndex("increment",4,5,0,0),0);
  assert.equal(nextIndex("decrement",0,5,0,0),4);
  assert.equal(nextIndex("random",0,0,0,0),-1);
  assert.equal(hash32(12,1),hash32(12,1));
});
test("factory presets cannot be shadowed",()=>{
  assert.equal(DEFAULT_PRESETS.length,19);
  for (const id of [
    "default:krea2","default:krea2-photo","default:krea2-anime","default:krea2-illustration",
    "default:krea2-3d","default:krea2-product","default:krea2-graphic",
    "default:h3","default:h3-first","default:h3-first-last","default:h3-last","default:h3-ref",
    "default:moss","default:moss-photo","default:moss-anime",
    "default:moss-illustration","default:moss-3d","default:moss-product","default:moss-graphic"
  ]) assert.ok(DEFAULT_PRESETS.some(p=>p.id===id), id);
  assert.ok(DEFAULT_PRESETS.every(p=>isDefaultPreset(p.id)));
  assert.deepEqual(getPreset("default:krea2",{length:0}),DEFAULT_PRESETS[0]);
  assert.deepEqual(validateUserPresets([
    {id:"default:krea2",name:"hack",text:"bad"},
    {id:"user:1",name:"Default / Krea 2 - Image",text:"bad"},
    {id:"user:2",name:"My preset",text:"Good"},
    {id:"user:3",name:"my preset",text:"Duplicate"}
  ]),[{id:"user:2",name:"My preset",text:"Good"}]);
});

test("presets use the correct model modalities and official H3 formats",()=>{
  const preset=id=>getPreset(id);
  const image=DEFAULT_PRESETS.filter(p=>p.id.startsWith("default:krea2")||p.id.startsWith("default:moss"));
  assert.ok(image.every(p=>!p.text.includes("integrated_multimodal_description:")));
  assert.match(preset("default:krea2-photo").text,/photograph/i);
  assert.match(preset("default:krea2-anime").text,/anime/i);
  assert.match(preset("default:moss").text,/image-generation model, not a video model/);
  for (const id of ["default:h3","default:h3-first","default:h3-first-last","default:h3-last"]) {
    for (const field of ["integrated_multimodal_description:","overall_soundscape:","non_diegetic_music:"])
      assert.ok(preset(id).text.includes(field),id+" missing "+field);
  }
  const ref=preset("default:h3-ref").text;
  for (const field of ["subject_definitions","summary","retention_analysis","detailed_description","overall_soundscape","non_diegetic_music"])
    assert.ok(ref.includes(field),"reference missing "+field);
  assert.match(preset("default:h3-first").text,/0\\.00 seconds|0\.00 seconds/);
  assert.match(preset("default:h3-first-last").text,/Picture 2/);
});
