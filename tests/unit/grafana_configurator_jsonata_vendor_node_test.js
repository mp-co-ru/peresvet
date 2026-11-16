const fs = require("fs");
const vm = require("vm");

const dashboardPath = process.argv[2];
const vendorPath = process.argv[3];
const dashboard = JSON.parse(fs.readFileSync(dashboardPath, "utf8"));
const javascript = dashboard.panels[0].options.onRender;
const start = javascript.indexOf("window.prsMethodParamJsonataLoad=function()");
const end = javascript.indexOf(",window.prsMethodParamPatchResponseJsonata=");
if (start < 0 || end < start) throw new Error("JSONata loader not found");
if (javascript.includes("cdn.jsdelivr.net") || javascript.includes("import(")) {
  throw new Error("configurator still loads JSONata from the network");
}
const loaderSrc = javascript.slice(start, end);

function installLoader() {
  const sandbox = {
    Promise,
    Error,
    appendCount: 0,
    lastScript: null,
  };
  sandbox.window = sandbox;
  sandbox.document = {
    documentElement: {},
    createElement(tag) {
      if (tag !== "script") throw new Error("unexpected element " + tag);
      return {src: "", async: false, onload: null, onerror: null};
    },
    head: {
      appendChild(el) {
        sandbox.appendCount += 1;
        sandbox.lastScript = el;
      },
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(loaderSrc, sandbox);
  return sandbox;
}

function loadLibrary(sandbox) {
  vm.runInContext(fs.readFileSync(vendorPath, "utf8"), sandbox);
  if (typeof sandbox.jsonata !== "function") {
    throw new Error("vendored JSONata did not set window.jsonata");
  }
}

(async function () {
  const sandbox = installLoader();
  const first = sandbox.prsMethodParamJsonataLoad();
  const second = sandbox.prsMethodParamJsonataLoad();
  if (first !== second) throw new Error("concurrent loads are not shared");
  if (!sandbox.lastScript || sandbox.lastScript.src !== "/grafana/public/vendor/jsonata-2.0.6.min.js") {
    throw new Error("loader did not request the local file");
  }
  loadLibrary(sandbox);
  sandbox.lastScript.onload();
  await first;
  if (sandbox.prsMethodParamJsonataLoadPending) throw new Error("pending load was not cleared");
  const again = sandbox.prsMethodParamJsonataLoad();
  await again;
  if (sandbox.appendCount !== 1) throw new Error("JSONata was requested more than once");
  const value = await sandbox.jsonata("a+1").evaluate({a: 2});
  if (value !== 3) throw new Error("JSONata evaluated to " + value);

  const failed = installLoader();
  const pending = failed.prsMethodParamJsonataLoad();
  failed.lastScript.onerror();
  let rejected = false;
  try {
    await pending;
  } catch (err) {
    rejected = String(err && err.message || err).includes("не удалось загрузить локальный файл");
  }
  if (!rejected) throw new Error("script error was not reported");
  if (failed.prsMethodParamJsonataLoadPending) throw new Error("failed load stayed pending");
})().catch(function (err) {
  console.error(err);
  process.exit(1);
});
