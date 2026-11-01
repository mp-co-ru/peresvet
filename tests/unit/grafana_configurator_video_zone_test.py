import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"

NODE_BEHAVIOR = r"""
const fs = require("fs");
const dash = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
const js = dash.panels[0].options.onRender;
function grab(name) {
  const key = name + "=function";
  const at = js.indexOf(key);
  if (at < 0) throw new Error("missing " + name);
  const start = js.indexOf("{", at);
  let depth = 0;
  for (let i = start; i < js.length; i++) {
    const ch = js[i];
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return js.slice(at, i + 1);
    }
  }
  throw new Error("unclosed " + name);
}
const window = {prsVideoZonePoints: []};
function prsVideoZoneStatus() {}
function prsVideoZonePaint() {}
eval(grab("prsVideoZoneUserPoint"));
eval(grab("prsVideoZoneEventPoint"));
eval(grab("prsVideoZoneEdgeHit"));
eval(grab("prsVideoZoneAddPoint"));
eval(grab("prsVideoZoneDot"));
eval(grab("prsVideoMediaBox"));
const svg = {getBoundingClientRect: () => ({left: 0, top: 0, width: 200, height: 100})};
window.prsVideoZonePoints = [[0, 0], [1, 0], [1, 1], [0, 1]];
prsVideoZoneAddPoint(svg, [0.5, 0.04]);
if (window.prsVideoZonePoints.length !== 5) {
  throw new Error("edge click did not insert: " + JSON.stringify(window.prsVideoZonePoints));
}
const inserted = window.prsVideoZonePoints[1];
if (Math.abs(inserted[0] - 0.5) > 0.02 || Math.abs(inserted[1]) > 0.02) {
  throw new Error("inserted off the edge: " + JSON.stringify(window.prsVideoZonePoints));
}
prsVideoZoneAddPoint(svg, [0.5, 0.5]);
if (window.prsVideoZonePoints.length !== 5) {
  throw new Error("interior click must not add a vertex: " + JSON.stringify(window.prsVideoZonePoints));
}
const wide = {
  getBoundingClientRect: () => ({left: 0, top: 0, width: 800, height: 450}),
  getScreenCTM: () => {
    const scale = 450;
    const ox = (800 - scale) / 2;
    const forward = {a: scale, b: 0, c: 0, d: scale, e: ox, f: 0};
    forward.inverse = () => ({a: 1 / scale, b: 0, c: 0, d: 1 / scale, e: -ox / scale, f: 0});
    return forward;
  },
  createSVGPoint() {
    return {
      x: 0,
      y: 0,
      matrixTransform(mat) {
        return {x: mat.a * this.x + mat.c * this.y + mat.e, y: mat.b * this.x + mat.d * this.y + mat.f};
      }
    };
  }
};
const rightClick = prsVideoZoneEventPoint(wide, {clientX: 800, clientY: 225});
if (!rightClick || Math.abs(rightClick[0] - 1) > 0.02 || Math.abs(rightClick[1] - 0.5) > 0.02) {
  throw new Error("right side of the frame mapped to " + JSON.stringify(rightClick));
}
window.prsVideoZonePoints = [[0.13, 0.32], [0.28, 0.32], [0.44, 0.82], [0.43, 0.98], [0.22, 0.98], [0.14, 0.59], [0.13, 0.46]];
const midX = (0.28 + 0.44) / 2;
const midY = (0.32 + 0.82) / 2;
prsVideoZoneAddPoint(wide, prsVideoZoneEventPoint(wide, {clientX: midX * 800, clientY: midY * 450}));
const onRight = window.prsVideoZonePoints[2];
if (!onRight || onRight[0] < 0.3 || Math.abs(onRight[1] - midY) > 0.04) {
  throw new Error("right-edge click inserted on the wrong side: " + JSON.stringify(window.prsVideoZonePoints));
}
const dot = prsVideoZoneDot(svg, 2, 0.2, 0.3, 3, false);
if (!dot.startsWith("<ellipse") || !dot.includes('rx="0.01500"') || !dot.includes('ry="0.03000"') || !dot.includes('fill="#ffd24a"')) {
  throw new Error("vertex is not a round pixel ellipse: " + dot);
}
const media = {
  getBoundingClientRect: () => ({left: 10, top: 20, width: 200, height: 100}),
  videoWidth: 100,
  videoHeight: 100,
  naturalWidth: 0,
  naturalHeight: 0
};
const box = prsVideoMediaBox(media);
if (Math.abs(box.left - 60) > 0.01 || Math.abs(box.top - 20) > 0.01 || Math.abs(box.width - 100) > 0.01 || Math.abs(box.height - 100) > 0.01) {
  throw new Error("content box " + JSON.stringify(box));
}
eval(grab("prsVideoZoneNorm"));
eval(grab("prsVideoZoneRead"));
eval(grab("prsVideoZoneInside"));
eval(grab("prsVideoZoneCollect"));
eval(grab("prsVideoZonePayload"));
const legacy = prsVideoZoneRead({points: [[0, 0], [1, 0], [1, 1], [0, 1]]});
if (legacy.length !== 1) throw new Error("legacy zone was not kept");
const many = prsVideoZoneRead({
  space: "normalized",
  zones: [
    [[0, 0], [0.2, 0], [0.2, 0.2], [0, 0.2]],
    [[0.6, 0.6], [1, 0.6], [1, 1], [0.6, 1]]
  ]
});
if (many.length !== 2) throw new Error("zones " + JSON.stringify(many));
if (prsVideoZoneRead({points: [[0, 0], [1, 0], [1, 1]], zones: []}).length !== 0) {
  throw new Error("empty zones must mean the whole frame");
}
window.prsVideoZoneFinished = [many[0]];
window.prsVideoZonePoints = many[1];
const stored = prsVideoZonePayload(prsVideoZoneCollect());
if (!stored.zones || stored.zones.length !== 2 || stored.points || stored.fullFrame != null) {
  throw new Error("payload " + JSON.stringify(stored));
}
if (stored.zones[0].length < 3 || stored.space != null) {
  throw new Error("zone polygon " + JSON.stringify(stored));
}
if (!prsVideoZoneInside([0.1, 0.1], many[0]) || prsVideoZoneInside([0.5, 0.5], many[0])) {
  throw new Error("inside test failed");
}
console.log("ok");
"""


def _parts():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    options = dashboard["panels"][0]["options"]
    return options["html"], options["css"], options["onRender"]


def test_video_zone_edit_contract():
    html, css, javascript = _parts()
    assert 'id="button-prsVideoZoneNew"' in html
    assert ">Добавить зону<" in html
    assert ">Удалить зону<" in html
    assert "prsVideoZoneHitLines=function" in javascript
    assert "prsVideoZoneInsertOnEdge=function" in javascript
    assert 'Кликните по зоне, которую нужно удалить.' in javascript
    assert "prsVideoZoneRead=function" in javascript
    assert "prsVideoZonePayload=function" in javascript
    assert "prsVideoZoneAddPoint(draft,pt)" in javascript
    assert 'if(prsPrevNodeId&&prsPrevNodeId!==t&&"function"==typeof prsHideVideoTagPreview)prsHideVideoTagPreview()' in javascript
    assert 'el.src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"' in javascript
    assert "prsVideoZoneDot(draft,i,pts[i][0],pts[i][1],9,!0)" in javascript
    assert "prsVideoZoneDot(draft,i,pts[i][0],pts[i][1],4,!1)" in javascript
    assert 'r="0.012"' not in javascript
    assert "<circle" not in javascript.split("prsVideoZonePaint=function", 1)[1].split("prsVideoZoneSetEditing=function", 1)[0]
    assert "prsVideoMediaBox=function" in javascript
    assert "prsVideoZoneSyncNow()" in javascript
    assert 'document.addEventListener("fullscreenchange",onFs)' in javascript
    assert 'new ResizeObserver(function(){prsVideoZoneSyncNow()})' in javascript
    assert '["#prs-video-zone-draft","#prs-video-zone-saved","#prs-video-recognition"]' in javascript
    assert ".prs-video-zone-draft{position:absolute;z-index:4;cursor:crosshair;pointer-events:all;overflow:hidden}" in css
    assert 'id="button-prsVideoResize"' in html
    assert "prsBindVideoResize=function" in javascript
    assert 'data-zi="' in javascript


def test_video_zone_edit_behavior():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    subprocess.run([node, "-e", NODE_BEHAVIOR, str(DASHBOARD_PATH)], check=True)
