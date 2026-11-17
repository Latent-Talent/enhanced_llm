// Prompt input mode uses ComfyUI's existing widget-backed STRING input slot.
// Native frontend widget-to-input conversion is deprecated: widgets and sockets
// coexist. Keep the original text in the widget as the disconnect fallback.

export function promptInputSlot(node) {
  const index=(node?.inputs??[]).findIndex(
    input=>input?.name==="prompt" || input?.widget?.name==="prompt"
  );
  return {index,connected:index>=0&&node.inputs[index]?.link!=null};
}

export function usesPromptInput(node) {
  return promptInputSlot(node).connected ||
    Boolean(node?.properties?.enhancedLLMUsePromptInput);
}

export function canEnhancePrompt(node, text) {
  if(promptInputSlot(node).connected) return true;
  if(usesPromptInput(node)) return false;
  return typeof text==="string" && Boolean(text.trim());
}
