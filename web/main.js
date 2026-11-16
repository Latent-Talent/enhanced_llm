import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { MODES, nextIndex } from "./cycle.mjs";
import { summarizeBatch, buttonLabel } from "./progress.mjs";
import { createTextareaResizeController, HEIGHT_PROPERTY, TEXTAREA_HEIGHTS } from "./resize.mjs";
import { DEFAULT_PRESETS, isDefaultPreset, getPreset, validateUserPresets } from "./presets.mjs";

const NODE = "LatentTalentEnhancedGenerateText";
const PRESETS_FILE = "enhanced_llm/presets.json";
const PANELS = new Set();
let userPresets = [];
let presetsLoaded = false;
let loading = null;

function stylesheet() {
  if (document.querySelector('link[data-eml-style]')) return;
  const link=document.createElement("link");
  link.rel="stylesheet";
  link.dataset.emlStyle="1";
  link.href=new URL("./styles.css",import.meta.url).href;
  document.head.append(link);
}
async function reloadPresets() {
  if(loading)return loading;
  loading=(async()=>{
    try {
      const response=await api.getUserData(PRESETS_FILE);
      if(response.ok)userPresets=validateUserPresets((await response.json()).presets);
      else if(response.status!==404)throw new Error("HTTP "+response.status);
      presetsLoaded=true;
    }catch(err){console.warn("[Enhanced LLM] Presets not loaded",err);presetsLoaded=false;}
    finally {
      loading=null;
      for(const panel of PANELS)panel.updatePresets();
    }
  })();
  return loading;
}
async function writePresets(next) {
  const normalized=validateUserPresets(next);
  const response=await api.storeUserData(PRESETS_FILE,JSON.stringify({version:1,presets:normalized}),{overwrite:true});
  if(response && !response.ok)throw new Error("HTTP "+response.status);
  userPresets=normalized;presetsLoaded=true;
  for(const panel of PANELS)panel.updatePresets();
}
function automaticSeed() {
  // Secure randomness when available, Math.random fallback for LAN HTTP
  // contexts. The cycle seed is intentionally not exposed to the user.
  if (globalThis.crypto?.getRandomValues) {
    const words = new Uint32Array(1);
    globalThis.crypto.getRandomValues(words);
    return words[0];
  }
  return (Math.random() * 0x100000000) >>> 0;
}
const fresh=()=>({version:1,sets:[{name:"Unsaved",items:[],step:0,shuffleSeed:0}],active:0,index:0});
function parseState(raw) {
  try{
    const x=typeof raw==="string"?JSON.parse(raw):raw;
    if(!Array.isArray(x?.sets)||!x.sets.length)return fresh();
    const sets=x.sets.slice(0,100).map(s=>({
      name:String(s?.name||"Unsaved").slice(0,100),
      items:(Array.isArray(s?.items)?s.items:[]).slice(0,500).map(v=>({
        text:String(v?.text??"").slice(0,100000),
        thinking:String(v?.thinking??"").slice(0,100000)
      })),
      step:Math.max(0,Math.floor(Number(s?.step)||0)),
      shuffleSeed:(Number(s?.shuffleSeed)||0)>>>0
    }));
    const active=Math.max(0,Math.min(sets.length-1,Math.floor(Number(x.active)||0)));
    const index=Math.max(0,Math.min(sets[active].items.length-1,Math.floor(Number(x.index)||0)));
    return {version:1,sets,active,index};
  }catch{return fresh();}
}
const field=(root,key)=>root.querySelector('[data-eml="'+key+'"]');
const ownWidget=(node,key)=>node.widgets?.find(w=>w.name===key);
const get=(node,key)=>ownWidget(node,key)?.value;
function set(node,key,value) {
  const widget=ownWidget(node,key);
  if(widget && widget.value!==value)widget.value=value;
  node.setDirtyCanvas?.(true,true);
}
const mkOption=(label,value)=>new Option(label,String(value));

function attach(node) {
  if(node.__emlPanel)return;
  stylesheet();
  const root=document.createElement("section");
  root.className="eml-panel";
  const resize=createTextareaResizeController(node);
  let textareaObserver=null;
  function restoreTextareaHeights() {
    resize.restore(node.properties?.[HEIGHT_PROPERTY],at("jailbreak-group").open);
    for (const key of Object.keys(TEXTAREA_HEIGHTS)) {
      const input=field(root,key);
      if(input)input.style.height=resize.size(key)+"px";
    }
  }
  // Static markup: user text and generated text only enter DOM via value/textContent.
  root.innerHTML=[
    '<textarea data-eml="prompt" rows="4" aria-label="Prompt" placeholder="prompt"></textarea>',
    '<div class="eml-row eml-toolbar eml-enhance-row"><button class="eml-primary" data-eml="enhance" title="Run only upstream inputs and the connected LLM">Enhance</button>',
    '<span class="eml-counter"><button data-eml="minus" title="Fewer enhancements">−</button><span data-eml="count">1</span><button data-eml="plus" title="More enhancements">+</button></span>',
    '<button data-eml="promote" title="Copy enhanced text into original prompt">↑</button><button data-eml="undo1">Undo</button></div>',
    '<label class="eml-toggle" title="Queue one full workflow run for each successful enhancement">',
    '<span class="eml-toggle-name">Queue Run for Each</span>',
    '<span class="eml-toggle-control"><input data-eml="run-each" type="checkbox" role="switch" aria-label="Queue Run for Each"><span class="eml-switch-track" aria-hidden="true"></span></span></label>',
    '<textarea data-eml="enhanced" rows="5" aria-label="Enhanced prompt" placeholder="enhanced_prompt"></textarea>',
    '<div class="eml-row eml-toolbar eml-results-row"><span class="eml-counter"><button data-eml="prev">−</button><span data-eml="position">0 / 0</span><button data-eml="next">+</button></span>',
    '<button data-eml="remove" title="Remove selected result">×</button><button data-eml="undo">Undo</button><button data-eml="redo">Redo</button><button data-eml="clear">Clear All</button></div>',
    '<div class="eml-row eml-setting eml-set-row"><label>Prompt Set</label><button data-eml="save-set" title="Save or rename set">Save</button><button data-eml="new-set" title="New empty prompt set">+</button>',
    '<select data-eml="sets" aria-label="Prompt Set"></select><button data-eml="delete-set" title="Delete selected set">×</button></div>',
    '<div class="eml-row eml-setting eml-cycle-row"><label>Prompt Cycle</label><select data-eml="cycle" aria-label="Prompt Cycle"></select></div>',
    '<div class="eml-divider"></div>',
    '<div class="eml-row eml-setting eml-preset-row"><label>Enhancement Preset</label><button data-eml="save-preset" title="Save user preset">Save</button>',
    '<button data-eml="save-as" title="Save as new preset">Save As</button><select data-eml="presets" aria-label="Enhancement Preset"></select>',
    '<button data-eml="delete-preset" title="Delete user preset">×</button></div>',
    '<textarea data-eml="instructions" rows="5" aria-label="Enhancement system prompt" placeholder="enhancement_text"></textarea>',
    '<details class="eml-jailbreak" data-eml="jailbreak-group"><summary>Jailbreak (optional)</summary>',
    '<textarea data-eml="jailbreak" rows="3" aria-label="Jailbreak prefix for enhancement system prompt" placeholder="Optional instructions added before the selected enhancement preset"></textarea></details>',
    '<div data-eml="rename" class="eml-row eml-rename" hidden><input data-eml="name" maxlength="100" aria-label="New name" placeholder="Name">',
    '<button data-eml="name-save">Save</button><button data-eml="name-cancel">Cancel</button></div>',
    '<div class="eml-status" data-eml="status" role="alert" aria-live="polite" hidden></div>'
  ].join("");
  const at=id=>field(root,id);
  // No permanent status footer; show feedback only when an error needs attention.
  const status=message=>{
    const text=String(message||"");
    at("status").textContent=text;
    at("status").hidden=!text;
  };
  const showButton=(done=0,total=0,running=false)=>{
    const button=at("enhance");
    button.textContent=buttonLabel(done,total,running);
    button.classList.toggle("eml-cancel",running);
    button.title=running
      ? "Cancel outstanding enhancements in this batch (does not remove full runs already queued)"
      : "Run only upstream inputs and the connected LLM";
    button.setAttribute("aria-label",button.textContent);
  };
  let state=parseState(get(node,"prompt_sets_json"));
  let undo=[],redo=[],count=1,nameKind=null,editing=false,busy=false,activeBatchId=null,poll=null;
  let submittingBatch=null;
  const seenJobs=new Set();
  const current=()=>state.sets[state.active];
  const selected=()=>current().items[state.index];
  const remember=()=>{undo.push(JSON.stringify(state));if(undo.length>60)undo.shift();redo=[];};
  const persist=()=>set(node,"prompt_sets_json",JSON.stringify(state));
  function renderSelection() {
    const items=current().items;
    state.index=items.length?Math.max(0,Math.min(items.length-1,state.index)):0;
    at("enhanced").value=selected()?.text||"";
    at("position").textContent=items.length?(state.index+1)+" / "+items.length:"0 / 0";
    at("prev").disabled=at("next").disabled=at("remove").disabled=items.length===0;
    at("clear").disabled=items.length===0;
    at("undo").disabled=at("undo1").disabled=undo.length===0;
    at("redo").disabled=redo.length===0;
    set(node,"enhanced_prompt",selected()?.text||"");
    set(node,"enhanced_thinking",selected()?.thinking||"");
    persist();
  }
  function renderSets(){
    at("sets").replaceChildren();
    state.sets.forEach((s,i)=>at("sets").add(mkOption(s.name,i)));
    at("sets").value=String(state.active);
    at("delete-set").disabled=state.sets.length===1;
    renderSelection();
  }
  function advanceCycle(){
    const set=current(),n=set.items.length,mode=get(node,"prompt_cycle")||"fixed";
    if(!n||mode==="fixed")return;
    if(mode==="shuffle"){
      if(set.step%n===0 || !set.shuffleSeed)set.shuffleSeed=automaticSeed();
      state.index=nextIndex("shuffle",state.index,n,set.shuffleSeed,set.step);
    }else if(mode==="random"){
      state.index=nextIndex("random",state.index,n,automaticSeed(),0);
    }else{
      state.index=nextIndex(mode,state.index,n,0,set.step);
    }
    set.step+=1;
    renderSelection();
  }
  function restore(stack,other){
    if(!stack.length)return;
    other.push(JSON.stringify(state));
    state=parseState(stack.pop());renderSets();
  }
  function addResult(item){
    const text=String(item?.text||"").trim();
    if(!text)return;
    const id=String(item?.job_id||"");
    if(!id || seenJobs.has(id))return;
    seenJobs.add(id);
    remember();current().items.push({text,thinking:String(item.thinking||"")});
    state.index=current().items.length-1;
    renderSelection();
    status("");
  }
  function selectPreset(id,resetText=true){
    const p=getPreset(id,userPresets)||DEFAULT_PRESETS[0];
    set(node,"enhancement_preset_id",p.id);at("presets").value=p.id;
    if(resetText){at("instructions").value=p.text;set(node,"enhancement_text",p.text);}
    at("save-preset").disabled=isDefaultPreset(p.id)||!presetsLoaded;
    at("delete-preset").disabled=isDefaultPreset(p.id)||!presetsLoaded;
  }
  function renderPresets(){
    const id=get(node,"enhancement_preset_id")||DEFAULT_PRESETS[0].id;
    at("presets").replaceChildren();
    const families=[
      ["Krea 2",p=>p.id.startsWith("default:krea2")],
      ["MiniMax H3",p=>p.id.startsWith("default:h3")],
      ["MOSS-Image",p=>p.id.startsWith("default:moss")],
    ];
    for(const [label,matches] of families){
      const group=document.createElement("optgroup");
      group.label=label+" · Default (read-only)";
      for(const p of DEFAULT_PRESETS.filter(matches))group.appendChild(mkOption(p.name,p.id));
      at("presets").appendChild(group);
    }
    if(userPresets.length){
      const group=document.createElement("optgroup");group.label="User Presets";
      for(const p of userPresets)group.appendChild(mkOption(p.name,p.id));
      at("presets").appendChild(group);
    }
    selectPreset(id,false);
  }
  const showRename=kind=>{
    nameKind=kind;at("rename").hidden=false;
    at("name").value=kind==="set" && current().name!=="Unsaved"?current().name:"";
    at("name").focus();
  };
  async function commitName(){
    const name=at("name").value.trim();
    if(!name)return status("Enter a name.");
    try{
      if(nameKind==="set"){
        if(state.sets.some((s,i)=>i!==state.active&&s.name.toLowerCase()===name.toLowerCase()))
          throw new Error("That prompt set name already exists.");
        remember();current().name=name;renderSets();status("");
      }else if(nameKind==="preset"){
        if(!presetsLoaded)throw new Error("User preset storage is unavailable.");
        if([...DEFAULT_PRESETS,...userPresets].some(p=>p.name.toLowerCase()===name.toLowerCase()))
          throw new Error("That preset name already exists.");
        const id="user:"+(globalThis.crypto?.randomUUID?.()||String(Date.now()));
        await writePresets([...userPresets,{id,name,text:at("instructions").value}]);
        selectPreset(id);status("");
      }
      nameKind=null;at("rename").hidden=true;
    }catch(err){status(err.message);}
  }
  at("prompt").oninput=()=>set(node,"prompt",at("prompt").value);
  at("enhanced").onfocus=()=>editing=false;
  at("enhanced").oninput=()=>{
    if(!editing){remember();editing=true;}
    if(!current().items.length){current().items.push({text:"",thinking:""});state.index=0;}
    current().items[state.index].text=at("enhanced").value;
    set(node,"enhanced_prompt",at("enhanced").value);
    at("position").textContent=(state.index+1)+" / "+current().items.length;
    persist();
  };
  at("enhanced").onblur=()=>{editing=false;renderSelection();};
  at("instructions").oninput=()=>set(node,"enhancement_text",at("instructions").value);
  at("jailbreak").oninput=()=>set(node,"jailbreak_text",at("jailbreak").value);
  at("jailbreak-group").ontoggle=()=>{
    const open=at("jailbreak-group").open;
    if(!node.properties)node.properties={};
    node.properties.enhancedLLMJailbreakOpen=open;
    resize.setJailbreakVisible(open);
  };
  at("minus").onclick=()=>{count=Math.max(1,count-1);at("count").textContent=count;};
  at("plus").onclick=()=>{count=Math.min(32,count+1);at("count").textContent=count;};
  at("run-each").onchange=()=>set(node,"queue_run_for_each",at("run-each").checked);
  at("promote").onclick=()=>{at("prompt").value=at("enhanced").value;set(node,"prompt",at("prompt").value);};
  at("prev").onclick=()=>{const n=current().items.length;if(n){state.index=(state.index+n-1)%n;renderSelection();}};
  at("next").onclick=()=>{const n=current().items.length;if(n){state.index=(state.index+1)%n;renderSelection();}};
  at("remove").onclick=()=>{
    if(!current().items.length)return;remember();current().items.splice(state.index,1);
    renderSelection();
  };
  at("clear").onclick=()=>{
    if(!current().items.length)return;remember();current().items=[];
    current().step=0;state.index=0;renderSelection();
  };
  at("undo").onclick=at("undo1").onclick=()=>restore(undo,redo);
  at("redo").onclick=()=>restore(redo,undo);
  at("save-set").onclick=()=>showRename("set");
  at("new-set").onclick=()=>{
    remember();state.sets.push({name:"Unsaved "+(state.sets.length+1),items:[],step:0,shuffleSeed:0});
    state.active=state.sets.length-1;state.index=0;renderSets();
  };
  at("delete-set").onclick=()=>{
    if(state.sets.length<=1)return;remember();state.sets.splice(state.active,1);
    state.active=0;state.index=0;renderSets();
  };
  at("sets").onchange=()=>{
    state.active=Number(at("sets").value);state.index=0;renderSelection();
  };
  for(const mode of MODES)at("cycle").add(mkOption(mode,mode));
  at("cycle").onchange=()=>{
    const mode=at("cycle").value;set(node,"prompt_cycle",mode);
    current().step=0;
    if(current().items.length&&mode==="shuffle"){
      current().shuffleSeed=automaticSeed();
      state.index=nextIndex("shuffle",0,current().items.length,current().shuffleSeed,0);
      current().step=1;
    }else if(current().items.length&&mode==="random"){
      state.index=nextIndex("random",0,current().items.length,automaticSeed(),0);
      current().step=1;
    }
    renderSelection();
  };
  at("presets").onchange=()=>selectPreset(at("presets").value);
  at("save-preset").onclick=async()=>{
    const id=get(node,"enhancement_preset_id");
    if(isDefaultPreset(id))return status("Default presets are read-only. Use Save As.");
    if(!presetsLoaded)return status("User preset storage unavailable.");
    try{
      await writePresets(userPresets.map(p=>p.id===id?{...p,text:at("instructions").value}:p));
      status("");
    }catch(err){status("Save failed: "+err.message);}
  };
  at("save-as").onclick=()=>showRename("preset");
  at("delete-preset").onclick=async()=>{
    const id=get(node,"enhancement_preset_id");
    if(isDefaultPreset(id))return status("Default presets cannot be deleted.");
    try{
      await writePresets(userPresets.filter(p=>p.id!==id));
      selectPreset(DEFAULT_PRESETS[0].id);status("");
    }catch(err){status("Delete failed: "+err.message);}
  };
  at("name-save").onclick=commitName;
  at("name-cancel").onclick=()=>{nameKind=null;at("rename").hidden=true;};
  at("name").onkeydown=e=>{
    if(e.key==="Enter"){e.preventDefault();commitName();}
    if(e.key==="Escape"){nameKind=null;at("rename").hidden=true;}
  };
  function monitorBatch(id){
    if(poll)clearInterval(poll);
    const refresh=async()=>{
      if(activeBatchId!==id)return;
      try{
        const r=await api.fetchApi("/enhanced_llm/batch/"+encodeURIComponent(id));
        if(!r.ok)throw new Error("HTTP "+r.status);
        const data=await r.json();
        if(activeBatchId!==id)return; // late response from an older batch
        const progress=summarizeBatch(data.jobs);
        showButton(progress.completed,progress.total,!progress.terminal);
        if(progress.failed || progress.fullRunErrors){
          status(progress.failed+" enhancement failures; "+
            progress.fullRunErrors+" full runs failed to queue.");
        }
        if(progress.terminal){
          if(poll){clearInterval(poll);poll=null;}
          activeBatchId=null;
          showButton(progress.completed,progress.total,false);
        }
      }catch(err){console.warn("[Enhanced LLM] Queue status:",err);}
    };
    poll=setInterval(refresh,1600);
    refresh();
  }
  at("enhance").onclick=async()=>{
    if(busy)return;
    if(activeBatchId){
      // Cancel only this node's enhancement jobs; never clear the global queue.
      busy=true;at("enhance").disabled=true;
      try{
        const id=activeBatchId;
        const response=await api.fetchApi(
          "/enhanced_llm/batch/"+encodeURIComponent(id)+"/cancel",{method:"POST"});
        const data=await response.json();
        if(!response.ok)throw new Error(data.error||"HTTP "+response.status);
        if(poll){clearInterval(poll);poll=null;}
        activeBatchId=null;
        const progress=summarizeBatch(data.jobs);
        showButton(progress.completed,progress.total,false);
        status("");
      }catch(err){status("Cancel failed: "+err.message);}
      finally{busy=false;at("enhance").disabled=false;}
      return;
    }
    if(!at("prompt").value.trim())return status("Enter an original prompt.");
    if(!at("instructions").value.trim())return status("Select or enter an enhancement preset.");
    if(!node.inputs?.some(i=>i.name==="clip"&&i.link!=null))
      return status("Connect a text-generation CLIP model.");
    if(app.processingQueue){
      return status("ComfyUI is already submitting prompts. Retry when submission finishes.");
    }
    busy=true;at("enhance").disabled=true;
    status("");
    showButton(0,count,true);
    let reserved=null;
    try{
      const snapshot=await app.graphToPrompt();
      const response=await api.fetchApi("/enhanced_llm/batch/reserve",{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          node_id:String(node.id),count,queue_run_for_each:at("run-each").checked,
          output:snapshot.output,workflow:snapshot.workflow,
          client_id:api.clientId||null
        })
      });
      const data=await response.json();
      if(!response.ok)throw new Error(data.error||"HTTP "+response.status);
      if(app.processingQueue)throw new Error("ComfyUI started submitting another queue request.");
      reserved=data;
      activeBatchId=data.batch_id;
      submittingBatch={
        ids:data.jobs.map(j=>j.job_id),
        next:0,
        current:null,
        submitted:[],
      };
      // ComfyUI invokes upstream beforeQueued -> graphToPrompt -> native
      // /prompt -> upstream afterQueued on *every* partial run. This honors
      // a connected seed node's configured fixed/increment/random mode and
      // updates its visible state. Never emulate seed math here.
      const queued=await app.queuePrompt(0,count,{queueNodeIds:[String(node.id)]});
      if(!queued && !submittingBatch.submitted.length){
        status("ComfyUI did not accept the enhancement batch.");
      }
    }catch(err){
      status("Queue failed: "+err.message);
    }finally{
      // Restore normal outputs before another workflow submission.
      const submitted=submittingBatch?.submitted||[];
      submittingBatch=null;
      set(node,"ui_action","pass");
      set(node,"enhancement_job_id","");
      if(reserved){
        try{
          const r=await api.fetchApi(
            "/enhanced_llm/batch/"+encodeURIComponent(reserved.batch_id)+"/finalize",{
              method:"POST",headers:{"Content-Type":"application/json"},
              body:JSON.stringify({submitted_job_ids:submitted})
            });
          if(!r.ok)throw new Error("HTTP "+r.status);
        }catch(err){
          status("Batch reconciliation failed: "+err.message);
        }
        monitorBatch(reserved.batch_id);
      }else{
        activeBatchId=null;
        showButton();
      }
      busy=false;at("enhance").disabled=false;
    }
  };
  const panel={
    updatePresets:renderPresets,
    hydrate(){
      // Widgets are restored after nodeCreated when loading a workflow.
      state=parseState(get(node,"prompt_sets_json"));
      at("prompt").value=String(get(node,"prompt")||"");
      at("cycle").value=String(get(node,"prompt_cycle")||"fixed");
      at("run-each").checked=Boolean(get(node,"queue_run_for_each"));
      renderSets();renderPresets();
      const saved=String(get(node,"enhancement_text")||"");
      if(saved)at("instructions").value=saved;
      else selectPreset(get(node,"enhancement_preset_id")||DEFAULT_PRESETS[0].id);
      at("jailbreak").value=String(get(node,"jailbreak_text")||"");
      const isExpanded=node.properties?.enhancedLLMJailbreakOpen;
      at("jailbreak-group").open=isExpanded==null
        ? Boolean(at("jailbreak").value) : Boolean(isExpanded);
      restoreTextareaHeights();
    },
    executed(result){
      const records=result?.enhanced_llm;
      if(Array.isArray(records))for(const item of records)addResult(item);
    },
    destroy(){
      if(poll)clearInterval(poll);
      textareaObserver?.disconnect();
      PANELS.delete(panel);
    }
  };
  PANELS.add(panel);
  node.__emlPanel=panel;
  for(const id of ["prompt","enhanced_prompt","enhanced_thinking","enhancement_text","jailbreak_text",
    "enhancement_preset_id","prompt_sets_json","prompt_cycle",
    "queue_run_for_each","ui_action","enhancement_job_id"]){
    const w=ownWidget(node,id);if(w)w.hidden=true;
  }
  const dom=node.addDOMWidget("enhanced_llm_panel","div",root,{
    serialize:false,hideOnZoom:false,
    getMinWidth:()=>480,
    getMinHeight:()=>resize.minHeight(),
    getHeight:()=>resize.minHeight()
  });
  dom.serialize=false;
  // Each successful native queue submission consumes one reserved job UUID.
  // The normal ComfyUI queue lifecycle updates upstream seed widgets.
  dom.beforeQueued=({isPartialExecution}={})=>{
    if(!isPartialExecution || !submittingBatch || submittingBatch.current)return;
    const id=submittingBatch.ids[submittingBatch.next++];
    if(!id)return;
    submittingBatch.current=id;
    set(node,"ui_action","enhance");
    set(node,"enhancement_job_id",id);
  };
  dom.afterQueued=({isPartialExecution}={})=>{
    if(!isPartialExecution || !submittingBatch?.current)return;
    submittingBatch.submitted.push(submittingBatch.current);
    submittingBatch.current=null;
  };
  // DOM widget first, followed by ComfyUI's native sampling and MTP controls.
  const index=node.widgets.indexOf(dom);
  if(index>=0){node.widgets.splice(index,1);node.widgets.unshift(dom);}
  const w=ownWidget(node,"enhanced_prompt");
  if(w)w.afterQueued=({isPartialExecution}={})=>{
    if(!isPartialExecution)advanceCycle();
  }; // partial enhancement queuing must not advance result cycling
  panel.hydrate();
  const requiredHeight=Number(node.computeSize?.()?.[1])||0;
  node.setSize?.([
    Math.max(node.size?.[0]||0,565),
    Math.max(node.size?.[1]||0,requiredHeight+12,920)
  ]);
  if(typeof ResizeObserver!=="undefined"){
    textareaObserver=new ResizeObserver(entries=>{
      for(const entry of entries){
        const key=entry.target.dataset.eml;
        if(key in TEXTAREA_HEIGHTS)resize.observedHeight(key,entry.target.offsetHeight);
      }
    });
    for(const key of Object.keys(TEXTAREA_HEIGHTS)) {
      const input=at(key);
      if(input)textareaObserver.observe(input);
    }
  }
  const prevConfigure=node.onConfigure;
  node.onConfigure=function(...args){
    const result=prevConfigure?.apply(this,args);
    queueMicrotask(()=>panel.hydrate());
    return result;
  };
  const prevExecuted=node.onExecuted;
  node.onExecuted=function(...args){
    prevExecuted?.apply(this,args);
    panel.executed(args[0]);
  };
  const prevRemoved=node.onRemoved;
  node.onRemoved=function(...args){
    panel.destroy();return prevRemoved?.apply(this,args);
  };
}

app.registerExtension({
  name:"LatentTalent.EnhancedLLM",
  async init(){stylesheet();await reloadPresets();},
  nodeCreated(node){
    if(node.comfyClass===NODE||node.type===NODE)attach(node);
  },
});
