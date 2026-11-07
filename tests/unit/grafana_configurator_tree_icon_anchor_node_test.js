const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const dashboardPath = process.argv[2];
const dashboard = JSON.parse(fs.readFileSync(dashboardPath, "utf8"));
const source = dashboard.panels[0].options.onRender;
const start = source.indexOf("prsTreePadToTypeIcon=function");
const end = source.indexOf(",prsLayoutTreeFromTypeIcon=function");
assert(start >= 0 && end > start, "type-icon anchor helpers were not found");

const context = {};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);

// Child type icon sits just to the right of the parent type icon.
// pad 28px, parent icon right 114, child icon left 78, gap 4 -> child moves to 118.
assert.strictEqual(context.prsTreePadToTypeIcon(28, 114, 78, 4), 68);
// Same anchor when the child type icon started further right.
assert.strictEqual(context.prsTreePadToTypeIcon(28, 114, 96, 4), 50);
// Already aligned: parent right + gap === child left.
assert.strictEqual(context.prsTreePadToTypeIcon(28, 114, 118, 4), 28);
assert.strictEqual(context.prsTreePadToTypeIcon(0, 10, 100, 4), 0);

console.log("configurator tree icon anchor ok");
