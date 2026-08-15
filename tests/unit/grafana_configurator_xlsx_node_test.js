const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const [dashboardPath, xlsxPath] = process.argv.slice(2);
const dashboard = JSON.parse(fs.readFileSync(dashboardPath, "utf8"));
const source = dashboard.panels[0].options.onRender;
const start = source.indexOf(
  'var Ze="",et={},tt="",rt={},prsTagDataExportSnapshot='
);
const end = source.indexOf(",setTagData=()=>", start);
assert(start >= 0 && end > start, "XLSX helper block was not found");

const XLSX = require(xlsxPath);
const button = { disabled: false };
const table = {
  clearCount: 0,
  empty() {
    this.clearCount += 1;
    return this;
  },
};
const textValues = {
  "#span-tagGetDataURL": "http://localhost/v1/data/?tagId=tag-1",
  "#div-nodeName": "Тег",
  "#div-nodeId": "tag-1",
};
let lastAlert = "";

function jquery(selector) {
  if (selector === "#tbody-tagData") return table;
  return {
    empty: () => table.empty(),
    text: () => textValues[selector] || "",
  };
}

const context = {
  Blob,
  TextEncoder,
  URL,
  btoa: (value) => Buffer.from(value, "binary").toString("base64"),
  console,
  fetch: null,
  n: jquery,
  setTimeout: (callback) => callback(),
  showAlert: (...args) => {
    lastAlert = String(args[3] || "");
  },
  window: {
    XLSX,
    confirm: () => true,
    location: { href: "http://localhost/grafana/" },
  },
  __prsConfiguratorGetEl: (id) =>
    id === "button-tagExportXlsx" ? button : null,
};
vm.createContext(context);
vm.runInContext(`${source.slice(start, end)};`, context);

function sampleSnapshot(dataPoints) {
  const response = { data: [] };
  return {
    tagName: "=Тестовый тег",
    tagId: "tag-1",
    method: "GET",
    url: "http://localhost/v1/data/?tagId=tag-1",
    params: { tagId: "tag-1", format: true },
    timestamp: "2026-08-15T09:00:00.000Z",
    httpStatus: 200,
    rawResponseText: JSON.stringify(response),
    response,
    dataPoints,
  };
}

function sheetRows(workbook, name) {
  return XLSX.utils.sheet_to_json(workbook.Sheets[name], {
    header: 1,
    raw: true,
    defval: "",
  });
}

async function main() {
  const longText = `Начало\n${"я".repeat(65000)}\nКонец`;
  const point = [
    -12.5,
    true,
    false,
    'Русский "текст"\nновая строка',
    "=SUM(A1:A2)",
    "+command",
    "-text",
    "@user",
    { nested: "значение", quote: '"', lines: "a\nb" },
    longText,
  ];
  const snapshot = sampleSnapshot([
    { tagId: "tag-1", seriesIndex: 0, pointIndex: 0, point },
  ]);
  snapshot.rawResponseText = JSON.stringify({
    data: [{ tagId: "tag-1", data: [point] }],
  });

  const workbook = context.prsBuildTagDataWorkbook(snapshot);
  assert.deepStrictEqual(Array.from(workbook.SheetNames), [
    "Metadata",
    "Data",
    "Raw response",
  ]);

  const bytes = XLSX.write(workbook, { bookType: "xlsx", type: "buffer" });
  const roundTrip = XLSX.read(bytes, { type: "buffer" });
  const dataRows = sheetRows(roundTrip, "Data");
  const rowsForValue = (index) =>
    dataRows.slice(1).filter((row) => row[3] === index);

  assert.strictEqual(rowsForValue(0)[0][6], -12.5);
  assert.strictEqual(typeof rowsForValue(0)[0][6], "number");
  assert.strictEqual(rowsForValue(1)[0][6], true);
  assert.strictEqual(typeof rowsForValue(1)[0][6], "boolean");
  assert.strictEqual(rowsForValue(2)[0][6], false);
  assert.strictEqual(rowsForValue(3)[0][6], point[3]);
  assert.strictEqual(rowsForValue(4)[0][6], "'=SUM(A1:A2)");
  assert.strictEqual(rowsForValue(5)[0][6], "'+command");
  assert.strictEqual(rowsForValue(6)[0][6], "'-text");
  assert.strictEqual(rowsForValue(7)[0][6], "'@user");

  const objectText = rowsForValue(8)
    .sort((left, right) => left[4] - right[4])
    .map((row) => row[6])
    .join("");
  assert.deepStrictEqual(JSON.parse(objectText), point[8]);

  const longRows = rowsForValue(9).sort((left, right) => left[4] - right[4]);
  assert(longRows.length >= 3);
  assert(longRows.every((row) => String(row[6]).length <= 30000));
  assert.strictEqual(longRows.map((row) => row[6]).join(""), longText);

  const metadataRows = sheetRows(roundTrip, "Metadata");
  assert(
    metadataRows.some(
      (row) => row[0] === "Tag name" && row[2] === "'=Тестовый тег"
    )
  );
  assert(metadataRows.some((row) => row[0] === "HTTP status" && row[2] === 200));

  const rawRows = sheetRows(roundTrip, "Raw response");
  const rawText = rawRows
    .slice(1)
    .filter((row) => row[0] === "UTF-8 JSON text")
    .sort((left, right) => left[1] - right[1])
    .map((row) => row[2])
    .join("");
  assert.strictEqual(rawText, snapshot.rawResponseText);

  const emptyWorkbook = context.prsBuildTagDataWorkbook(sampleSnapshot([]));
  assert.strictEqual(sheetRows(emptyWorkbook, "Data").length, 1);

  context.prsTagDataExportSnapshot = snapshot;
  context.prsInvalidateTagDataExport();
  assert.strictEqual(context.prsTagDataExportSnapshot, null);
  assert.strictEqual(button.disabled, true);
  assert(table.clearCount > 0);

  context.fetch = async () => ({ ok: false, status: 500 });
  button.disabled = false;
  const clearsBeforeError = table.clearCount;
  assert.strictEqual(await context.getTagData(), false);
  assert(table.clearCount > clearsBeforeError);
  assert.strictEqual(button.disabled, true);
  assert(lastAlert.includes("HTTP 500"));

  context.fetch = async () => ({
    ok: true,
    status: 200,
    text: async () => '{"data":[]}',
  });
  assert.strictEqual(await context.getTagData(), true);
  assert.strictEqual(button.disabled, false);
  assert.deepStrictEqual(
    Array.from(context.prsTagDataExportSnapshot.dataPoints),
    []
  );

  const sensitive = context.prsSensitiveRequestKeys({
    url: "http://localhost/v1/data/?API_KEY=value",
    params: { nested: { Authorization: "value" }, normal: "ok" },
  });
  assert.deepStrictEqual(Array.from(sensitive).sort(), [
    "api_key",
    "authorization",
  ]);
  let confirmationCount = 0;
  context.window.confirm = () => {
    confirmationCount += 1;
    return false;
  };
  context.prsTagDataExportSnapshot = {
    ...sampleSnapshot([]),
    url: "http://localhost/v1/data/?token=value",
  };
  assert.strictEqual(await context.prsExportTagDataXlsx(), false);
  assert.strictEqual(confirmationCount, 1);

  const oversized = sampleSnapshot([]);
  oversized.rawResponseText = "x".repeat(context.prsXlsxMaxRawBytes + 1);
  assert.throws(
    () => context.prsValidateExportSnapshot(oversized),
    /25 MiB/
  );

  const scripts = [];
  context.window.XLSX = undefined;
  context.prsXlsxLibraryPromise = null;
  context.document = {
    baseURI: "http://localhost/grafana/",
    querySelector: () => scripts[0] || null,
    createElement: () => {
      const listeners = {};
      return {
        dataset: {},
        addEventListener: (name, callback) => {
          listeners[name] = callback;
        },
        dispatch: (name) => listeners[name](),
        remove() {
          const index = scripts.indexOf(this);
          if (index >= 0) scripts.splice(index, 1);
        },
      };
    },
    head: {
      appendChild: (script) => scripts.push(script),
    },
  };

  const firstLoad = context.prsLoadXlsxLibrary();
  const failedScript = scripts[0];
  failedScript.dispatch("error");
  await assert.rejects(firstLoad, /локальную библиотеку XLSX/);
  assert.strictEqual(scripts.length, 0);
  assert.strictEqual(context.prsXlsxLibraryPromise, null);

  const secondLoad = context.prsLoadXlsxLibrary();
  const retryScript = scripts[0];
  assert.notStrictEqual(retryScript, failedScript);
  context.window.XLSX = XLSX;
  retryScript.dispatch("load");
  assert.strictEqual(await secondLoad, XLSX);

  console.log("embedded XLSX helpers and workbook round-trip passed");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
