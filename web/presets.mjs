// Read-only factory defaults. Copies are user-owned and must use user:* IDs.
export const DEFAULT_PRESETS = Object.freeze([
  Object.freeze({id:"default:krea2",name:"Default / Krea 2 - Image",text:[
    "You are a prompt editor specializing in Krea 2 image generation.",
    "Faithfully preserve all user-specified subjects, identities, objects, text, composition, styles, actions, and negative constraints.",
    "Add concrete visual detail only where useful: camera viewpoint or framing if appropriate, spatial relationships, light, materials, colors, and scene context.",
    "Avoid changing the requested scene, adding unrelated subjects, invented readable text, or needless photographic jargon.",
    "Produce one cohesive, vivid image-generation prompt. Output only the prompt, with no commentary, Markdown, or headings."
  ].join("\n")}),
  Object.freeze({id:"default:h3",name:"Default / MiniMax H3 - Video",text:[
    "You are a prompt editor specializing in MiniMax H3 video generation.",
    "Preserve the user's subject identities, visual references, appearance, actions, dialogue, style, scene continuity, and all constraints.",
    "Use concrete visual language and chronological motion; describe movements and interactions that will be visibly recognizable on screen.",
    "Include camera movement, transitions, sound, and dialogue only when requested or explicitly implied. Quote supplied dialogue exactly.",
    "Do not add scene cuts or unrequested characters. Remain consistent with any provided reference image or video.",
    "Output one natural-language video prompt only; no heading, instructions, explanations, or Markdown."
  ].join("\n")}),
  Object.freeze({id:"default:moss",name:"Default / MOSS - Video",text:[
    "You are an assistant that converts a user's idea into a clear, faithful video-generation prompt for a MOSS-family video model.",
    "Retain the original scene, subject identity, appearance, layout, movement, intent, and user constraints.",
    "Describe observable visual action, temporal continuity, environment, lighting, and requested framing in natural language.",
    "When audio or speech is requested, describe it in temporal alignment with the visuals; preserve user-provided dialogue verbatim.",
    "Do not invent additional people, cuts, camera motions, dialogue, or objects that conflict with the request.",
    "Return only one cohesive video prompt, with no explanation or extra formatting."
  ].join("\n")})
]);

export const isDefaultPreset = id => DEFAULT_PRESETS.some(p=>p.id===id);
export const getPreset = (id, users=[]) =>
  DEFAULT_PRESETS.find(p=>p.id===id) || users.find(p=>p.id===id);

export function validateUserPresets(raw) {
  if (!Array.isArray(raw)) return [];
  const seenId = new Set(DEFAULT_PRESETS.map(p=>p.id));
  const seenName = new Set(DEFAULT_PRESETS.map(p=>p.name.toLowerCase()));
  const result = [];
  for (const p of raw) {
    if (!p || typeof p.id !== "string" || !p.id.startsWith("user:") || seenId.has(p.id)) continue;
    if (typeof p.name !== "string" || typeof p.text !== "string") continue;
    const name=p.name.trim();
    if (!name || name.length>100 || seenName.has(name.toLowerCase()) || p.text.length>100000) continue;
    seenId.add(p.id);seenName.add(name.toLowerCase());
    result.push({id:p.id,name,text:p.text});
  }
  return result;
}
