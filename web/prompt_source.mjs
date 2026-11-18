// The dedicated force-input socket is placed after ComfyUI's native audio
// inputs. A legacy widget-backed prompt socket is still accepted so that
// previously saved workflows with a connected prompt continue to work.

export function promptInputSlots(node) {
  const result=[];
  for (let index=0; index<(node?.inputs?.length??0); index++) {
    const slot=node.inputs[index];
    if (slot?.name==="prompt_input" || slot?.name==="prompt" ||
        slot?.widget?.name==="prompt") {
      result.push({index, connected:slot?.link!=null});
    }
  }
  return result;
}

export function promptInputSlot(node) {
  // Prefer the new socket, including for disconnecting it on promotion.
  const slots=promptInputSlots(node);
  const preferred=(node?.inputs??[]).findIndex(input=>input?.name==="prompt_input");
  return slots.find(slot=>slot.index===preferred)??slots[0]??{index:-1,connected:false};
}

export function usesPromptInput(node) {
  // No separate toggle and no duplicated state: the wire controls visibility.
  return promptInputSlots(node).some(slot=>slot.connected);
}

export function canEnhancePrompt(node,text) {
  return usesPromptInput(node) || (typeof text==="string" && Boolean(text.trim()));
}
