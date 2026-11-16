import test from "node:test";
import assert from "node:assert/strict";
import {
  createTextareaResizeController,
  HEIGHT_PROPERTY,
  BASE_PANEL_HEIGHT,
  TEXTAREA_HEIGHTS,
} from "../../web/resize.mjs";

function makeNode() {
  return {
    size: [565, 880],
    properties: {},
    changes: [],
    computeSize() {
      return [565, 200 + controller.minHeight()];
    },
    setSize(size) {this.size = size;this.changes.push([...size]);},
    setDirtyCanvas() {this.dirty = true;},
  };
}
let controller;

test("expanding a textarea grows the node by the same amount", () => {
  const node = makeNode();
  controller = createTextareaResizeController(node);
  controller.observedHeight("prompt", TEXTAREA_HEIGHTS.prompt);
  assert.equal(controller.observedHeight("prompt", 176), true);
  assert.equal(node.size[1], 960);
  assert.equal(node.properties[HEIGHT_PROPERTY].prompt, 176);
  assert.equal(controller.minHeight(), BASE_PANEL_HEIGHT + 80);
  assert.equal(node.dirty, true);
});

test("shrinking a textarea shrinks the node without discarding other allocated space", () => {
  const node = makeNode();
  controller = createTextareaResizeController(node);
  controller.observedHeight("enhanced", 116);
  controller.observedHeight("enhanced", 296);
  assert.equal(node.size[1], 1060);
  controller.observedHeight("enhanced", 146);
  assert.equal(node.size[1], 910);
});

test("restoring stored textarea heights doesn't re-expand the restored node", () => {
  const node = makeNode();
  node.size[1] = 1050;
  controller = createTextareaResizeController(node);
  controller.restore({prompt: 236, enhanced: 150, instructions: 116});
  assert.equal(controller.minHeight(), BASE_PANEL_HEIGHT + 174);
  assert.equal(controller.observedHeight("prompt", 236), false);
  assert.equal(controller.observedHeight("enhanced", 150), false);
  assert.equal(node.size[1], 1050);
  assert.equal(node.changes.length, 0);
  controller.observedHeight("prompt", 256);
  assert.equal(node.size[1], 1070);
});

test("invalid dimensions and initial observers do not resize", () => {
  const node = makeNode();
  controller = createTextareaResizeController(node);
  controller.restore({prompt: 999999, enhanced: "oops", instructions: 0});
  assert.equal(controller.size("prompt"), TEXTAREA_HEIGHTS.prompt);
  assert.equal(controller.size("enhanced"), TEXTAREA_HEIGHTS.enhanced);
  assert.equal(controller.observedHeight("prompt", 96), false);
  assert.equal(controller.observedHeight("prompt", 96), false);
  assert.equal(controller.observedHeight("not_a_field", 200), false);
  assert.equal(node.changes.length, 0);
});

test("revealing optional jailbreak textarea grows node; hiding restores it",()=>{
  const node=makeNode();
  controller=createTextareaResizeController(node);
  assert.equal(controller.observedHeight("jailbreak",88),false);
  assert.equal(controller.setJailbreakVisible(true),true);
  assert.equal(node.size[1],976);
  assert.equal(controller.observedHeight("jailbreak",88),false);
  assert.equal(controller.observedHeight("jailbreak",128),true);
  assert.equal(node.size[1],1016);
  assert.equal(node.properties[HEIGHT_PROPERTY].jailbreak,128);
  assert.equal(controller.setJailbreakVisible(false),true);
  assert.equal(node.size[1],880);
  assert.equal(controller.observedHeight("jailbreak",170),false);
});
