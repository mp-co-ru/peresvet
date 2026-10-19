const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const dashboardPath = process.argv[2];
const dashboard = JSON.parse(fs.readFileSync(dashboardPath, "utf8"));
const source = dashboard.panels[0].options.onRender;
const start = source.indexOf("/*prsJsonEditorStart*/");
const end = source.indexOf("/*prsJsonEditorEnd*/");
assert(start >= 0 && end > start, "json editor block was not found");

const context = { window: {}, JSON };
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);

const broken = '"source": {"hostTopic": "zigbee2mqtt", "createDevices": true}';
const error = context.prsJsonErrorText(broken);
assert.strictEqual(error, "Строка 1, символ 9: невалидный JSON");
assert.strictEqual(context.prsJsonErrorAt(broken), 8);

const valid = {
  source: {
    hostTopic: "zigbee2mqtt",
    createDevices: true,
    checkDeviceOnStart: true,
    parentId: null,
  },
};
const pretty = JSON.stringify(valid, null, 2);
assert.strictEqual(context.prsJsonErrorText(pretty), "");
assert.strictEqual(context.prsJsonErrorText("   "), "");
assert.strictEqual(context.prsJsonErrorText(""), "");

const highlighted = context.prsJsonHighlightHtml(pretty, -1);
assert(highlighted.includes('class="prs-json-str">"hostTopic"'));
assert(highlighted.includes('class="prs-json-bool">true'));
assert(highlighted.includes('class="prs-json-null">null'));

const marked = context.prsJsonHighlightHtml(broken, 8);
assert(marked.includes('class="prs-json-bad">:'));
assert(!marked.includes("prs-json-line"));

assert.strictEqual(context.prsJsonErrorLine(broken), 1);
assert.strictEqual(context.prsJsonErrorLine(pretty), 0);
assert.strictEqual(context.prsJsonLineCount(""), 1);
assert.strictEqual(context.prsJsonLineCount("a\nb\n"), 3);
const multi = '{\n"a": 1}\n"b"';
function plain(html) {
  return html
    .replace(/<[^>]+>/g, "")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}
assert.strictEqual(plain(context.prsJsonHighlightHtml(pretty, -1)), pretty);
assert.strictEqual(plain(context.prsJsonHighlightHtml(broken, 8)), broken);
assert.strictEqual(plain(context.prsJsonHighlightHtml(multi, context.prsJsonErrorAt(multi))), multi);
const box = context.prsJsonErrorBarBox(3, 18.85, 8);
assert.strictEqual(box.top, 8 + 2 * 18.85);
assert.strictEqual(box.height, 18.85);
assert.strictEqual(context.prsJsonErrorBarBox(0, 18, 8), null);
assert.strictEqual(context.prsJsonErrorLine(multi), 3);
const gutter = context.prsJsonGutterHtml(multi, 3);
assert(gutter.includes('class="prs-json-gutter-line">1</span>'));
assert(gutter.includes('class="prs-json-gutter-line is-bad">3</span>'));
assert.strictEqual((gutter.match(/prs-json-gutter-line/g) || []).length, 3);

const alerts = [];
const textarea = {
  value: broken,
  classList: {
    contains(name) {
      return name === "value-changed";
    },
  },
};
context.__prsConfiguratorGetEl = function (id) {
  return id === "input-prsJsonConfigString" ? textarea : null;
};
context.showAlert = function (box, messageBox, icon, text) {
  alerts.push(text);
};
assert.strictEqual(context.prsJsonEditorBlockSave(), true);
assert.deepStrictEqual(alerts, ["Конфигурация: " + error]);

textarea.value = pretty;
alerts.length = 0;
assert.strictEqual(context.prsJsonEditorBlockSave(), false);
assert.deepStrictEqual(alerts, []);

let formatted = "";
textarea.value = '{"a":1,"b":true}';
textarea.classList.contains = () => false;
context.onInputChange = function (event) {
  formatted = event.target.value;
};
context.prsJsonEditorRefresh = function () {};
context.prsJsonEditorFormat();
assert.strictEqual(formatted, '{\n  "a": 1,\n  "b": true\n}');
