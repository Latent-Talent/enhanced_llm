import test from "node:test";
import assert from "node:assert/strict";
import {nameValidationError} from "../../web/name_dialog.mjs";
import {readFileSync} from "node:fs";

const source=readFileSync(new URL("../../web/name_dialog.mjs",import.meta.url),"utf8");

test("name validation",()=>{
  assert.equal(nameValidationError(""),"Enter a name.");
  assert.equal(nameValidationError("  "),"Enter a name.");
  assert.match(nameValidationError("a".repeat(101)),/100 characters/);
  assert.match(nameValidationError("bad\nname"),/control characters/);
  assert.equal(nameValidationError("Sample Set"),"");
  assert.equal(nameValidationError("  Spaces  "),"");
  assert.equal(nameValidationError("新提示词"),"");
});

test("native popup has focus, form submission and error handling",()=>{
  assert.match(source,/document\.createElement\("dialog"\)/);
  assert.match(source,/element\.showModal\(\)/);
  assert.match(source,/element\.addEventListener\("close",dispose/);
  assert.match(source,/form\.addEventListener\("submit",async event=>/);
  assert.match(source,/await onSave\(name\)/);
  assert.match(source,/input\.focus\(\)/);
  assert.match(source,/element\.remove\(\)/);
  assert.match(source,/element\.close\(\)/);
  assert.match(source,/error\.setAttribute\("role","alert"\)/);
});
