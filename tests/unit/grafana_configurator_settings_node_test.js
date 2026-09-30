const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const dashboardPath = process.argv[2];
const dashboard = JSON.parse(fs.readFileSync(dashboardPath, "utf8"));
const source = dashboard.panels[0].options.onRender;
const start = source.indexOf("prsNodesSortedByName=function()");
const end = source.indexOf(",addNode=", start);
assert(start >= 0 && end > start, "sortList block was not found");

const store = {};
const localStorage = {
  getItem(key) {
    return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null;
  },
  setItem(key, value) {
    store[key] = String(value);
  },
};

function makeEl(attrs, label) {
  const node = {
    nodeType: 1,
    id: attrs.id || "",
    attributes: Object.assign({}, attrs),
    childNodes: [],
    parentNode: null,
    _label: label
      ? { textContent: label }
      : null,
    getAttribute(name) {
      const value = this.attributes[name];
      return value == null || value === "" ? null : String(value);
    },
    querySelector(selector) {
      if (selector === ":scope > .prs-tree-label") return this._label;
      return null;
    },
    appendChild(child) {
      if (child.parentNode) {
        const index = child.parentNode.childNodes.indexOf(child);
        if (index >= 0) child.parentNode.childNodes.splice(index, 1);
      }
      child.parentNode = this;
      this.childNodes.push(child);
      return child;
    },
  };
  return node;
}

function treeItem(id, label, extra) {
  return makeEl(Object.assign({ id, role: "treeitem" }, extra || {}), label);
}

function groupFor(item, children) {
  const group = makeEl({ id: "group_" + item.id, role: "group" });
  (children || []).forEach((child) => group.appendChild(child));
  return group;
}

const context = {
  localStorage,
  prsNodeLabel(node) {
    const label = node && node.querySelector(":scope > .prs-tree-label");
    return String((label && label.textContent) || (node && node.id) || "").trim();
  },
};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);

function names(group) {
  return group.childNodes
    .filter((node) => node.getAttribute("role") === "treeitem")
    .map((node) => context.prsNodeLabel(node));
}

function sortedByName(flag) {
  store["prs.configurator.sortNodesAlphabetically"] = flag ? "true" : "false";
}

// Type comes before prsIndex. Within one type the flag-off order stays prsIndex.
sortedByName(false);
const indexGroup = makeEl({ id: "group_parent", role: "group" });
indexGroup.appendChild(treeItem("z", "Якорь", { "data-prs-index": "2", objectClass: "prsObject" }));
indexGroup.appendChild(treeItem("a", "Альфа", { "data-prs-index": "1", objectClass: "prsTag" }));
indexGroup.appendChild(treeItem("b", "Бета", { "data-prs-index": "3", objectClass: "prsObject" }));
context.sortList(indexGroup);
assert.deepStrictEqual(names(indexGroup), ["Якорь", "Бета", "Альфа"]);

// Without prsIndex, turning the flag off restores insertion order.
sortedByName(false);
const platformGroup = makeEl({ id: "group_platform", role: "group" });
platformGroup.appendChild(treeItem("late", "Альфа", { "data-prs-platform-order": "2" }));
platformGroup.appendChild(treeItem("early", "Якорь", { "data-prs-platform-order": "1" }));
context.sortList(platformGroup);
assert.deepStrictEqual(names(platformGroup), ["Якорь", "Альфа"]);

// The flag sorts visible siblings by name, with numeric chunks.
sortedByName(true);
const alphaGroup = makeEl({ id: "group_alpha", role: "group" });
["тег 10", "Альфа", "тег 2", "Бета"].forEach((label, index) => {
  alphaGroup.appendChild(
    treeItem("n" + index, label, { "data-prs-index": String(10 - index) })
  );
});
context.sortList(alphaGroup);
assert.deepStrictEqual(names(alphaGroup), ["Альфа", "Бета", "тег 2", "тег 10"]);

// Type stays ahead of the name: objects, then tags, and only then the name.
sortedByName(true);
const typed = makeEl({ id: "group_typed", role: "group" });
typed.appendChild(treeItem("tag-a", "Альфа", { objectClass: "prsTag", "data-prs-index": "1" }));
typed.appendChild(treeItem("obj-ya", "Якорь", { objectClass: "prsObject", "data-prs-index": "9" }));
typed.appendChild(treeItem("tag-b", "Бета", { objectClass: "prsTag", "data-prs-index": "2" }));
typed.appendChild(treeItem("obj-a", "Абрикос", { objectClass: "prsObject", "data-prs-index": "8" }));
typed.appendChild(treeItem("alert-a", "Авария", { objectClass: "prsAlert", "data-prs-index": "0" }));
context.sortList(typed);
assert.deepStrictEqual(names(typed), ["Абрикос", "Якорь", "Альфа", "Бета", "Авария"]);

// A nested group stays with its tree item.
sortedByName(true);
const nested = makeEl({ id: "group_nested", role: "group" });
const parentB = treeItem("b", "Бета", { "data-bs-target": "#group_b" });
const child = treeItem("child", "Вложенный");
const parentA = treeItem("a", "Альфа", { "data-bs-target": "#group_a" });
nested.appendChild(parentB);
nested.appendChild(groupFor(parentB, [child]));
nested.appendChild(parentA);
context.sortList(nested);
assert.deepStrictEqual(
  nested.childNodes.map((node) => node.id),
  ["a", "b", "group_b"]
);
assert.strictEqual(nested.childNodes[2].childNodes[0].id, "child");

console.log("configurator settings sort ok");
