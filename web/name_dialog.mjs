/* Standalone modal for naming prompt sets and presets.
 * Lives in the document top layer; does not alter ComfyUI node layout.
 */
let nextId=0;

export function nameValidationError(value){
  const name=String(value??"").trim();
  if(!name)return "Enter a name.";
  if(name.length>100)return "Names must be 100 characters or fewer.";
  if(/[\u0000-\u001f\u007f]/.test(name))return "Names cannot contain control characters.";
  return "";
}

export function openNameDialog({title,description,initialName="",onSave,onClose=()=>{}}){
  if(typeof onSave!=="function")throw new TypeError("onSave must be a function");
  const element=document.createElement("dialog");
  const id="eml-name-title-"+(++nextId);
  element.className="eml-name-dialog";
  element.setAttribute("aria-labelledby",id);
  element.setAttribute("aria-modal","true");

  const form=document.createElement("form");
  form.className="eml-name-form";
  form.noValidate=true;

  const heading=document.createElement("h2");
  heading.id=id;
  heading.textContent=title;
  const help=document.createElement("p");
  help.className="eml-name-description";
  help.textContent=description;
  help.id=id+"-description";
  element.setAttribute("aria-describedby",help.id);

  const label=document.createElement("label");
  label.className="eml-name-label";
  label.textContent="Name";
  const input=document.createElement("input");
  input.type="text";
  input.name="name";
  input.maxLength=100;
  input.required=true;
  input.autocomplete="off";
  input.placeholder="Enter a name";
  input.value=initialName;
  label.append(input);

  const error=document.createElement("p");
  error.className="eml-name-error";
  error.id=id+"-error";
  error.hidden=true;
  error.setAttribute("role","alert");
  input.setAttribute("aria-describedby",error.id);

  const actions=document.createElement("div");
  actions.className="eml-name-actions";
  const cancel=document.createElement("button");
  cancel.type="button";
  cancel.className="eml-name-cancel";
  cancel.textContent="Cancel";
  const save=document.createElement("button");
  save.type="submit";
  save.className="eml-name-save";
  save.textContent="Save";
  actions.append(cancel,save);
  form.append(heading,help,label,error,actions);
  element.append(form);

  let closed=false;
  let saving=false;
  const setError=message=>{
    error.textContent=message;
    error.hidden=!message;
    input.setAttribute("aria-invalid",message?"true":"false");
  };
  const dispose=()=>{
    if(closed)return;
    closed=true;
    element.remove();
    onClose();
  };
  const close=()=>{
    if(closed||saving)return;
    if(element.open)element.close();
    else dispose();
  };
  element.addEventListener("close",dispose,{once:true});
  cancel.addEventListener("click",close);
  input.addEventListener("input",()=>setError(""));
  form.addEventListener("submit",async event=>{
    event.preventDefault();
    if(saving)return;
    const name=input.value.trim();
    const problem=nameValidationError(name);
    if(problem){setError(problem);input.focus();return;}
    saving=true;
    input.disabled=true;
    cancel.disabled=true;
    save.disabled=true;
    save.textContent="Saving…";
    setError("");
    try{
      await onSave(name);
      element.close();
    }catch(err){
      setError(err instanceof Error?err.message:String(err));
      input.focus();
      input.select();
    }finally{
      saving=false;
      input.disabled=false;
      cancel.disabled=false;
      save.disabled=false;
      save.textContent="Save";
    }
  });
  document.body.append(element);
  try{
    element.showModal();
    input.focus();
    if(initialName)input.select();
  }catch(err){
    dispose();
    throw err;
  }
  return {close,element};
}
