const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const dashboardPath = process.argv[2];
const dashboard = JSON.parse(fs.readFileSync(dashboardPath, "utf8"));
const source = dashboard.panels[0].options.onRender;
const start = source.indexOf("/*prsConnectorConfigStart*/");
const end = source.indexOf("/*prsConnectorConfigEnd*/");
assert(start >= 0 && end > start, "connector config block was not found");

function createElement(tag) {
  const node = {
    tag,
    className: "",
    id: "",
    htmlFor: "",
    type: "",
    value: "",
    checked: false,
    placeholder: "",
    rows: 0,
    step: "",
    spellcheck: true,
    textContent: "",
    children: [],
    attrs: {},
    listeners: {},
    _classes: new Set(),
    _html: "",
  };
  node.classList = {
    toggle(name, on) {
      if (on) node._classes.add(name);
      else node._classes.delete(name);
    },
    contains(name) {
      return node._classes.has(name);
    },
    add(name) {
      node._classes.add(name);
    },
    remove(name) {
      node._classes.delete(name);
    },
  };
  node.setAttribute = (key, value) => {
    node.attrs[key] = String(value);
  };
  node.getAttribute = (key) => (key in node.attrs ? node.attrs[key] : null);
  node.appendChild = (child) => {
    child.parent = node;
    node.children.push(child);
    return child;
  };
  node.addEventListener = (type, fn) => {
    node.listeners[type] = fn;
  };
  node.querySelectorAll = (sel) => {
    const out = [];
    const walk = (item) => {
      if (
        sel === ".prs-connector-config-field" &&
        String(item.className).includes("prs-connector-config-field")
      ) {
        out.push(item);
      }
      if (sel === "input,select,textarea" && ["input", "select", "textarea"].includes(item.tag)) {
        out.push(item);
      }
      (item.children || []).forEach(walk);
    };
    node.children.forEach(walk);
    return out;
  };
  node.querySelector = (sel) => node.querySelectorAll(sel)[0] || null;
  node.replaceChildren = () => {
    node.children.length = 0;
  };
  return node;
}

const textarea = { value: "", classList: { contains() { return false; } } };
const box = createElement("div");
box.classList.add("d-none");
const list = createElement("div");
const note = createElement("div");
const editor = createElement("div");
const changed = [];
const context = {
  JSON,
  document: { createElement, activeElement: null },
  window: {},
  __prsConfiguratorGetEl(id) {
    return {
      "input-prsJsonConfigString": textarea,
      "div-prsConnectorConfigFields": box,
      "prs-connector-config-list": list,
      "prs-connector-config-note": note,
      "prs-json-editor-node": editor,
    }[id] || null;
  },
  onInputChange(event) {
    changed.push(event.target.value);
  },
  prsJsonEditorRefresh() {},
};
context.window = context;
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);

const read = context.prsConnectorConfigReadPath;
const write = context.prsConnectorConfigWritePath;
const obj = { source: { hostTopic: "zigbee2mqtt", createDevices: true }, keep: 1 };
assert.strictEqual(read(obj, "source.hostTopic"), "zigbee2mqtt");
write(obj, "source.parentId", "", false);
assert.strictEqual(obj.source.parentId, "");
write(obj, "source.parentId", undefined, true);
assert.strictEqual("parentId" in obj.source, false);
assert.strictEqual(obj.keep, 1);

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}
assert.deepStrictEqual(plain(context.prsConnectorConfigCoerce({ type: "integer" }, "502")), { value: 502 });
assert.deepStrictEqual(plain(context.prsConnectorConfigCoerce({ type: "integer" }, "")), { remove: true });
assert.deepStrictEqual(plain(context.prsConnectorConfigCoerce({ type: "integer" }, "1.5")), { invalid: true });
assert.deepStrictEqual(plain(context.prsConnectorConfigCoerce({ type: "boolean" }, false)), { value: false });
assert.deepStrictEqual(plain(context.prsConnectorConfigCoerce({ type: "json" }, '{"a":1}')), { value: { a: 1 } });

const offline = context.prsConnectorConfigNoteText({
  source: "cache",
  connectorAvailable: false,
  fields: [{ key: "source.hostTopic", type: "string" }],
});
assert(offline.includes("не на связи"));
assert.strictEqual(
  context.prsConnectorConfigNoteText({ source: "connector", connectorAvailable: true, fields: [{ key: "a", type: "string" }] }),
  ""
);
assert(context.prsConnectorConfigNoteText({ source: "none", fields: [] }).includes("JSON"));

textarea.value = JSON.stringify({
  source: { hostTopic: "zigbee2mqtt", createDevices: false },
  untouched: { mode: "keep" },
});
const payload = {
  source: "cache",
  connectorAvailable: false,
  fields: [
    { key: "source", name: "Источник", description: "Группа", type: "object" },
    {
      key: "source.hostTopic",
      name: "Корневой топик <b>",
      description: "Топик MQTT",
      type: "string",
      example: "zigbee2mqtt",
    },
    { key: "source.createDevices", name: "Создавать устройства", type: "boolean" },
    {
      key: "log.level",
      name: "Уровень журнала",
      type: "string",
      enum: ["DEBUG", "INFO", "WARNING", "ERROR"],
      example: "INFO",
    },
  ],
};
context.prsConnectorConfigExample = payload;
context.window.prsConnectorConfigExample = payload;
context.prsConnectorRenderConfigFields(payload);
assert.strictEqual(box.classList.contains("d-none"), false);
assert.strictEqual(box.classList.contains("is-form"), true);
assert.strictEqual(editor.classList.contains("d-none"), true);
assert(note.textContent.includes("не на связи"));
const groups = list.children.filter((child) => child.className === "prs-connector-config-group");
assert.strictEqual(groups.length, 1);
assert.strictEqual(groups[0].textContent, "Источник");
const rows = list.querySelectorAll(".prs-connector-config-field");
assert.strictEqual(rows.length, 3);
assert.strictEqual(rows[0].children[0].textContent, "Корневой топик <b>");
assert.strictEqual(rows[0].children[0].children[0].textContent, "source.hostTopic");
assert.strictEqual(rows[0].children[0].children[1].getAttribute("title"), "Топик MQTT");
assert.strictEqual(rows[0].children[1].value, "zigbee2mqtt");
assert.strictEqual(rows[1].children[1].checked, false);
rows[0].children[1].value = "home/zigbee";
rows[0].children[1].listeners.change();
const saved = JSON.parse(textarea.value);
assert.strictEqual(saved.source.hostTopic, "home/zigbee");
assert.strictEqual(saved.source.createDevices, false);
assert.strictEqual(saved.untouched.mode, "keep");
assert.strictEqual(changed.length, 1);

rows[2].children[1].value = "WARNING";
rows[2].children[1].listeners.change();
assert.strictEqual(JSON.parse(textarea.value).log.level, "WARNING");

textarea.value = JSON.stringify({ source: { hostTopic: "from-json", createDevices: true } });
context.prsConnectorSyncConfigFieldsFromJson();
assert.strictEqual(rows[0].children[1].value, "from-json");
assert.strictEqual(rows[1].children[1].checked, true);

textarea.value = JSON.stringify({ log: { level: "ERROR" } });
const withDefault = {
  source: "connector",
  connectorAvailable: true,
  fields: [
    {
      key: "log.level",
      name: "Уровень журнала",
      type: "string",
      enum: ["DEBUG", "INFO", "WARNING", "ERROR"],
      example: "INFO",
      default: "INFO",
    },
    {
      key: "log.fileName",
      name: "Файл журнала",
      type: "string",
      example: "logs/a.log",
      default: "logs/a.log",
    },
  ],
  example: { source: {}, log: { level: "INFO", fileName: "logs/a.log", maxBytes: 10 } },
};
context.prsConnectorConfigExample = withDefault;
context.window.prsConnectorConfigExample = withDefault;
context.prsConnectorRenderConfigFields(withDefault);
const rows2 = list.querySelectorAll(".prs-connector-config-field");
assert.strictEqual(rows2[0].querySelector("input,select,textarea").value, "ERROR");
assert.strictEqual(rows2[1].querySelector("input,select,textarea").value, "logs/a.log");
const sample = list.children.find((child) => child.className === "prs-connector-config-sample");
const sampleText = sample.children.map((child) => child.textContent).join("\n");
assert(sampleText.includes("maxBytes"));
assert.strictEqual(
  sample.children[0].children[0].getAttribute("title"),
  "Образец целиком. В конфигурацию узла не записывается."
);
rows2[0].querySelector("input,select,textarea").value = "WARNING";
rows2[0].querySelector("input,select,textarea").listeners.change();
const saved2 = JSON.parse(textarea.value);
assert.strictEqual(saved2.log.level, "WARNING");
assert.strictEqual("fileName" in saved2.log, false);
assert.strictEqual("maxBytes" in saved2, false);

context.prsConnectorRenderConfigFields({ source: "none", fields: [], connectorAvailable: false });
assert.strictEqual(editor.classList.contains("d-none"), false);
assert(note.textContent.includes("JSON"));
assert.strictEqual(list.children.length, 0);

context.prsConnectorResetConfigForm();
assert.strictEqual(box.classList.contains("d-none"), true);
assert.strictEqual(editor.classList.contains("d-none"), false);
assert.strictEqual(note.textContent, "");
