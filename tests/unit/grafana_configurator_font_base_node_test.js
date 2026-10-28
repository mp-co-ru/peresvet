const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const dashboardPath = process.argv[2];
const dashboard = JSON.parse(fs.readFileSync(dashboardPath, "utf8"));
const source = dashboard.panels[0].options.onRender;
const start = source.indexOf("prsFontBasePx=function");
const end = source.indexOf("prsApplyFontBase=function", start);
assert(start >= 0 && end > start, "prsFontBasePx was not found");

const context = {};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);

assert.strictEqual(context.prsFontBasePx(null), 16);
assert.strictEqual(context.prsFontBasePx(undefined), 16);
assert.strictEqual(context.prsFontBasePx(""), 16);
assert.strictEqual(context.prsFontBasePx("abc"), 16);
assert.strictEqual(context.prsFontBasePx("16"), 16);
assert.strictEqual(context.prsFontBasePx("20"), 20);
assert.strictEqual(context.prsFontBasePx("18.9"), 18);
assert.strictEqual(context.prsFontBasePx("9"), 10);
assert.strictEqual(context.prsFontBasePx("99"), 32);

console.log("configurator font base ok");
