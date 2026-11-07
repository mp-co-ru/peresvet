const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const dashboardPath = process.argv[2];
const dashboard = JSON.parse(fs.readFileSync(dashboardPath, "utf8"));
const source = dashboard.panels[0].options.onRender;
const start = source.indexOf("prsNextTreeLoad=function");
const end = source.indexOf(",prsLoadDataStoragesUnder=function", start);
assert(start >= 0 && end > start, "tree load generation helpers were not found");

const context = {};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);

function row() {
  const attrs = {};
  const node = {
    isConnected: true,
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
    },
    setAttribute(name, value) {
      attrs[name] = String(value);
    },
    removeAttribute(name) {
      delete attrs[name];
    },
  };
  return node;
}

const node = row();
const first = context.prsNextTreeLoad(node);
node.setAttribute("aria-expanded", "true");
assert.strictEqual(context.prsTreeLoadAlive(node, first), true);

const second = context.prsNextTreeLoad(node);
assert.strictEqual(context.prsTreeLoadAlive(node, first), false);
assert.strictEqual(context.prsTreeLoadAlive(node, second), true);

node.removeAttribute("aria-expanded");
assert.strictEqual(context.prsTreeLoadAlive(node, second), false);

node.setAttribute("aria-expanded", "true");
node.isConnected = false;
assert.strictEqual(context.prsTreeLoadAlive(node, second), false);

console.log("configurator tree load generation ok");
