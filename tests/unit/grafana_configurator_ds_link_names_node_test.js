const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const dashboardPath = process.argv[2];
const dashboard = JSON.parse(fs.readFileSync(dashboardPath, "utf8"));
const source = dashboard.panels[0].options.onRender;
const start = source.indexOf("prsDsTagPathLabel=function");
const end = source.indexOf("prsDsTagPathLoad=function");
assert(start >= 0 && end > start, "tag path helpers were not found");

const context = {};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);

const index = {
  "obj-1": {id: "obj-1", cn: "Линия Цесис", parentId: "", root: "objects"},
  "folder-1": {id: "folder-1", cn: "Видео", parentId: "obj-1", root: "objects"},
  "tag-1": {id: "tag-1", cn: "Камера", parentId: "folder-1", root: "objects"},
  "tag-loose": {id: "tag-loose", cn: "Свободный", parentId: "", root: "tags"},
};

assert.strictEqual(
  context.prsDsTagPathLabel(index, "tag-1"),
  "Линия Цесис → Видео → Камера"
);
assert.strictEqual(context.prsDsTagPathLabel(index, "tag-loose"), "Свободный");
assert.strictEqual(context.prsDsTagPathLabel(index, "missing"), "");
function same(actual, expected) {
  assert.strictEqual(JSON.stringify(actual), JSON.stringify(expected));
}

same(context.prsDsTagOpenPath(index, "tag-1"), [
  "objects",
  "obj-1",
  "folder-1",
  "tag-1",
]);
same(context.prsDsTagOpenPath(index, "tag-loose"), ["tags", "tag-loose"]);
same(context.prsDsTagOpenPath(index, "missing"), []);

same(context.prsDsLinkStoreRows({attributes: {prsStore: {table: "t_tag-1"}}}), [
  ["Таблица", "t_tag-1"],
]);
same(
  context.prsDsLinkStoreRows({
    attributes: {prsStore: '{"directory":"/archive/video","retentionHours":72}'},
  }),
  [
    ["Каталог", "/archive/video"],
    ["Срок хранения, ч", "72"],
  ]
);
same(
  context.prsDsLinkStoreRows({attributes: {prsStore: {table: "t_a", tableName: "ignored"}}}),
  [["Таблица", "t_a"]]
);
same(context.prsDsLinkStoreRows({attributes: {}}), []);
same(context.prsDsLinkStoreRows(null), []);

console.log("configurator data-storage link names ok");
