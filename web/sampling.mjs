// Descriptive sampling presets for the native ComfyUI TextGenerateV2 sampler.
// These are starting points for prompt enhancement, not model-specific guarantees.
// IMPORTANT: DynamicCombo child widgets are named sampling_mode.<field>.
// Never create a second seed input or modify seed, thinking, MTP, or template.
const preset=(id,name,description,values)=>Object.freeze({
  id,name,description,values:Object.freeze(values)
});
export const SAMPLING_PRESETS=Object.freeze([
  preset("faithful","Faithful / Precise",
    "Conservative rewriting: best for exact details, reference constraints, layout and required wording.",
    {max_length:1024,temperature:0.40,top_k:40,top_p:0.85,min_p:0.06,repetition_penalty:1.05,presence_penalty:0.00}),
  preset("balanced","Balanced / Recommended",
    "General-purpose enhancement. Adds helpful visual detail without as much prompt drift.",
    {max_length:1024,temperature:0.70,top_k:64,top_p:0.92,min_p:0.05,repetition_penalty:1.05,presence_penalty:0.00}),
  preset("creative","Creative / Detailed",
    "More varied texture, lighting and atmosphere. Review for invented or inconsistent details.",
    {max_length:1536,temperature:0.90,top_k:80,top_p:0.95,min_p:0.03,repetition_penalty:1.05,presence_penalty:0.00}),
  preset("exploratory","High Variety / Exploratory",
    "Broader candidate sampling for alternative ideas; greater chance of drifting from the original.",
    {max_length:1536,temperature:1.10,top_k:120,top_p:0.98,min_p:0.02,repetition_penalty:1.03,presence_penalty:0.00}),
  preset("structured","Structured / Long Output",
    "More consistent, longer output for MiniMax H3 reference/video formats and multi-section prompts.",
    {max_length:2048,temperature:0.55,top_k:40,top_p:0.90,min_p:0.05,repetition_penalty:1.05,presence_penalty:0.00})
]);

const allFields=Object.keys(SAMPLING_PRESETS[0].values);
const nameOf=field=>field==="max_length"?"max_length":"sampling_mode."+field;
const widgetOf=(node,name)=>node.widgets?.find(w=>w.name===name);
const linked=(node,name)=>node.inputs?.some(i=>i.name===name&&i.link!=null)??false;

export function matchingSamplingPreset(node) {
  if(widgetOf(node,"sampling_mode")?.value!=="on")return null;
  for(const candidate of SAMPLING_PRESETS) {
    if(allFields.every(field=>{
      const name=nameOf(field),widget=widgetOf(node,name);
      return !linked(node,name)&&widget&&
        Number.isFinite(Number(widget.value))&&
        Math.abs(Number(widget.value)-candidate.values[field])<0.00001;
    }))return candidate;
  }
  return null;
}

export function applySamplingPreset(node,id) {
  const selected=SAMPLING_PRESETS.find(p=>p.id===id);
  if(!selected)throw new Error("Unknown LLM sampling preset.");
  const mode=widgetOf(node,"sampling_mode");
  if(!mode)throw new Error("Native Sampling Mode widget is unavailable.");
  if(linked(node,"sampling_mode"))throw new Error("Sampling Mode is connected and cannot be changed by a preset.");
  if(mode.value!=="on") {
    // Native dynamic combo creates its children when switched on.
    mode.value="on";
    mode.callback?.call(mode,"on");
  }
  const skipped=[],missing=[],targets=[];
  for(const field of allFields) {
    const name=nameOf(field);
    if(linked(node,name)){skipped.push(field);continue;}
    const w=widgetOf(node,name);
    if(!w){missing.push(field);continue;}
    targets.push([w,selected.values[field],field]);
  }
  if(missing.length)throw new Error("Native sampling widgets not found: "+missing.join(", "));
  const changed=[];
  for(const [w,value,field] of targets) {
    if(Number(w.value)===value)continue;
    w.value=value;
    w.callback?.call(w,value);
    changed.push(field);
  }
  node.setDirtyCanvas?.(true,true);
  return {preset:selected,changed,skipped,matched:matchingSamplingPreset(node)?.id===id};
}
