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
class BrowserURL extends URL {}
let objectUrlCreated = 0;
let objectUrlRevoked = 0;
BrowserURL.createObjectURL = () => {
  objectUrlCreated += 1;
  return "blob:peresvet-test";
};
BrowserURL.revokeObjectURL = () => {
  objectUrlRevoked += 1;
};

let nextTimerId = 1;
const timers = [];
function scheduleTimer(callback, delay) {
  const timer = { id: nextTimerId++, callback, delay, active: true };
  timers.push(timer);
  return timer.id;
}
function clearScheduledTimer(id) {
  const timer = timers.find((item) => item.id === id);
  if (timer) timer.active = false;
}
function runScheduledTimer(delay) {
  const timer = timers.find((item) => item.active && item.delay === delay);
  assert(timer, `active ${delay}ms timer was not found`);
  timer.active = false;
  timer.callback();
}

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
  TextDecoder,
  URL: BrowserURL,
  btoa: (value) => Buffer.from(value, "binary").toString("base64"),
  clearTimeout: clearScheduledTimer,
  console,
  fetch: null,
  n: jquery,
  setTimeout: scheduleTimer,
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

function assertLiteralStringCells(workbook) {
  for (const sheetName of workbook.SheetNames) {
    const sheet = workbook.Sheets[sheetName];
    for (const [address, cell] of Object.entries(sheet)) {
      if (address.startsWith("!")) continue;
      if (cell.t === "s") {
        assert.strictEqual(cell.f, undefined);
        assert.strictEqual(typeof cell.v, "string");
      }
    }
  }
}

async function main() {
  const longText = `Начало\n${"я".repeat(65000)}\nКонец`;
  const emojiBoundaryText = `${"a".repeat(29999)}😀z`;
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
    emojiBoundaryText,
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
  assertLiteralStringCells(workbook);

  const bytes = XLSX.write(workbook, { bookType: "xlsx", type: "buffer" });
  const roundTrip = XLSX.read(bytes, { type: "buffer" });
  assertLiteralStringCells(roundTrip);
  const dataRows = sheetRows(roundTrip, "Data");
  const rowsForValue = (index) =>
    dataRows.slice(1).filter((row) => row[3] === index);

  assert.strictEqual(rowsForValue(0)[0][6], -12.5);
  assert.strictEqual(typeof rowsForValue(0)[0][6], "number");
  assert.strictEqual(rowsForValue(1)[0][6], true);
  assert.strictEqual(typeof rowsForValue(1)[0][6], "boolean");
  assert.strictEqual(rowsForValue(2)[0][6], false);
  assert.strictEqual(rowsForValue(3)[0][6], point[3]);
  assert.strictEqual(rowsForValue(4)[0][6], "=SUM(A1:A2)");
  assert.strictEqual(rowsForValue(5)[0][6], "+command");
  assert.strictEqual(rowsForValue(6)[0][6], "-text");
  assert.strictEqual(rowsForValue(7)[0][6], "@user");

  const objectText = rowsForValue(8)
    .sort((left, right) => left[4] - right[4])
    .map((row) => row[6])
    .join("");
  assert.deepStrictEqual(JSON.parse(objectText), point[8]);

  const longRows = rowsForValue(9).sort((left, right) => left[4] - right[4]);
  assert(longRows.length >= 3);
  assert(longRows.every((row) => String(row[6]).length <= 30000));
  assert.strictEqual(longRows.map((row) => row[6]).join(""), longText);

  const emojiRows = rowsForValue(10).sort((left, right) => left[4] - right[4]);
  assert.strictEqual(emojiRows.length, 2);
  assert(emojiRows.every((row) => String(row[6]).length <= 30000));
  assert.strictEqual(emojiRows.map((row) => row[6]).join(""), emojiBoundaryText);
  assert(!/^[\uDC00-\uDFFF]/.test(emojiRows[1][6]));
  assert(!/[\uD800-\uDBFF]$/.test(emojiRows[0][6]));

  const metadataRows = sheetRows(roundTrip, "Metadata");
  assert(
    metadataRows.some(
      (row) => row[0] === "Tag name" && row[2] === "=Тестовый тег"
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
  const rawBase64 = rawRows
    .slice(1)
    .filter((row) => row[0] === "Base64 of exact UTF-8 response")
    .sort((left, right) => left[1] - right[1])
    .map((row) => row[2])
    .join("");
  assert.strictEqual(
    Buffer.from(rawBase64, "base64").toString("utf8"),
    snapshot.rawResponseText
  );

  const emptyWorkbook = context.prsBuildTagDataWorkbook(sampleSnapshot([]));
  assert.strictEqual(sheetRows(emptyWorkbook, "Data").length, 1);

  let anchorClicked = 0;
  let anchorRemoved = 0;
  context.document = {
    createElement: () => ({
      click: () => {
        anchorClicked += 1;
      },
      remove: () => {
        anchorRemoved += 1;
      },
    }),
    body: { appendChild: () => {} },
  };
  context.prsDownloadTagDataXlsx(
    new Uint8Array([1, 2, 3]),
    sampleSnapshot([])
  );
  assert.strictEqual(anchorClicked, 1);
  assert.strictEqual(objectUrlCreated, 1);
  assert.strictEqual(objectUrlRevoked, 0);
  runScheduledTimer(1000);
  assert.strictEqual(objectUrlRevoked, 1);
  assert.strictEqual(anchorRemoved, 1);

  context.prsTagDataExportSnapshot = snapshot;
  context.prsInvalidateTagDataExport();
  assert.strictEqual(context.prsTagDataExportSnapshot, null);
  assert.strictEqual(button.disabled, true);
  assert(table.clearCount > 0);

  const response = (text, options = {}) => ({
    ok: options.ok !== false,
    status: options.status || 200,
    headers: {
      get: (name) =>
        name.toLowerCase() === "content-length"
          ? options.contentLength ?? null
          : null,
    },
    body: options.body || null,
    text: async () => text,
  });

  context.fetch = async () => response("", { ok: false, status: 500 });
  button.disabled = false;
  const clearsBeforeError = table.clearCount;
  assert.strictEqual(await context.getTagData(), false);
  assert(table.clearCount > clearsBeforeError);
  assert.strictEqual(button.disabled, true);
  assert(lastAlert.includes("HTTP 500"));

  context.fetch = async () => response('{"data":[]}');
  assert.strictEqual(await context.getTagData(), true);
  assert.strictEqual(button.disabled, false);
  assert.deepStrictEqual(
    Array.from(context.prsTagDataExportSnapshot.dataPoints),
    []
  );

  context.fetch = async () => response("{invalid");
  assert.strictEqual(await context.getTagData(), false);
  assert.strictEqual(context.prsTagDataExportSnapshot, null);
  assert.strictEqual(button.disabled, true);
  assert(lastAlert.includes("Некорректный JSON"));

  const pendingFetches = [];
  context.fetch = () =>
    new Promise((resolve) => {
      pendingFetches.push(resolve);
    });
  const staleRequest = context.getTagData();
  const latestRequest = context.getTagData();
  pendingFetches[1](response('{"data":[],"request":"latest"}'));
  assert.strictEqual(await latestRequest, true);
  const latestRaw = context.prsTagDataExportSnapshot.rawResponseText;
  pendingFetches[0](response('{"data":[],"request":"stale"}'));
  assert.strictEqual(await staleRequest, false);
  assert.strictEqual(
    context.prsTagDataExportSnapshot.rawResponseText,
    latestRaw
  );

  let earlyBodyCancelled = 0;
  await assert.rejects(
    context.prsReadResponseText(
      response("", {
        contentLength: String(context.prsXlsxMaxRawBytes + 1),
        body: {
          cancel: async () => {
            earlyBodyCancelled += 1;
          },
        },
      })
    ),
    /25 MiB/
  );
  assert.strictEqual(earlyBodyCancelled, 1);
  assert.strictEqual(
    await context.prsReadResponseText(
      response("{}", { contentLength: String(context.prsXlsxMaxRawBytes) })
    ),
    "{}"
  );

  const originalRawLimit = context.prsXlsxMaxRawBytes;
  context.prsXlsxMaxRawBytes = 4;
  let streamCancelled = 0;
  const streamChunks = [
    new Uint8Array([65, 66, 67]),
    new Uint8Array([68, 69]),
  ];
  await assert.rejects(
    context.prsReadResponseText(
      response("", {
        body: {
          getReader: () => ({
            read: async () =>
              streamChunks.length
                ? { done: false, value: streamChunks.shift() }
                : { done: true },
            cancel: async () => {
              streamCancelled += 1;
            },
            releaseLock: () => {},
          }),
        },
      })
    ),
    /25 MiB/
  );
  assert.strictEqual(streamCancelled, 1);
  context.prsXlsxMaxRawBytes = originalRawLimit;

  const sensitive = context.prsSensitiveRequestKeys({
    url: "http://user:pass@localhost/v1/data/?API_KEY=value&access_token=x",
    params: {
      nested: { Authorization: "value", client_secret: "x" },
      "x-api-key": "x",
      auth: "x",
      normal: "ok",
    },
  });
  assert.deepStrictEqual(Array.from(sensitive).sort(), [
    "access_token",
    "api_key",
    "auth",
    "authorization",
    "client_secret",
    "url_userinfo",
    "x-api-key",
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

  const validMetrics = {
    rawBytes: context.prsXlsxMaxRawBytes,
    snapshotBytes: context.prsXlsxMaxSnapshotBytes,
    dataRows: context.prsXlsxMaxDataRows,
    workbookCells: context.prsXlsxMaxWorkbookCells,
  };
  assert.strictEqual(context.prsValidateExportMetrics(validMetrics), validMetrics);
  for (const [field, message] of [
    ["rawBytes", /25 MiB/],
    ["snapshotBytes", /32 MiB/],
    ["dataRows", /500000/],
    ["workbookCells", /2000000/],
  ]) {
    assert.throws(
      () =>
        context.prsValidateExportMetrics({
          ...validMetrics,
          [field]: validMetrics[field] + 1,
        }),
      message
    );
  }

  const scripts = [];
  const partialXlsx = { utils: {} };
  assert.strictEqual(context.prsIsXlsxReady(XLSX), true);
  assert.strictEqual(context.prsIsXlsxReady(partialXlsx), false);
  assert.strictEqual(context.prsIsXlsxReady({ utils: {}, write() {} }), false);
  context.window.XLSX = partialXlsx;
  assert.throws(
    () => context.prsBuildTagDataWorkbook(sampleSnapshot([])),
    /API локальной библиотеки XLSX не готов/
  );
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

  const staleExistingScript = {
    dataset: { prsXlsx: "0.18.5" },
    remove() {
      const index = scripts.indexOf(this);
      if (index >= 0) scripts.splice(index, 1);
    },
  };
  scripts.push(staleExistingScript);
  const firstLoad = context.prsLoadXlsxLibrary();
  const incompleteScript = scripts[0];
  assert.notStrictEqual(incompleteScript, staleExistingScript);
  assert.strictEqual(context.window.XLSX, undefined);
  context.window.XLSX = { utils: { book_new() {} } };
  incompleteScript.dispatch("load");
  await assert.rejects(firstLoad, /API XLSX неполон/);
  assert.strictEqual(scripts.length, 0);
  assert.strictEqual(context.prsXlsxLibraryPromise, null);
  assert.strictEqual(context.window.XLSX, partialXlsx);

  const secondLoad = context.prsLoadXlsxLibrary();
  const failedScript = scripts[0];
  failedScript.dispatch("error");
  await assert.rejects(secondLoad, /локальную библиотеку XLSX/);
  assert.strictEqual(scripts.length, 0);
  assert.strictEqual(context.prsXlsxLibraryPromise, null);
  assert.strictEqual(context.window.XLSX, partialXlsx);

  const thirdLoad = context.prsLoadXlsxLibrary();
  const timedOutScript = scripts[0];
  runScheduledTimer(10000);
  await assert.rejects(thirdLoad, /Истекло время/);
  assert.strictEqual(scripts.length, 0);
  assert.strictEqual(context.prsXlsxLibraryPromise, null);
  assert.strictEqual(context.window.XLSX, partialXlsx);

  const fourthLoad = context.prsLoadXlsxLibrary();
  const retryScript = scripts[0];
  assert.notStrictEqual(retryScript, failedScript);
  assert.notStrictEqual(retryScript, timedOutScript);
  context.window.XLSX = XLSX;
  retryScript.dispatch("load");
  assert.strictEqual(await fourthLoad, XLSX);
  assert.strictEqual(context.prsXlsxLibraryPromise, null);
  assert.strictEqual(context.prsIsXlsxReady(context.window.XLSX), true);
  const loadedScriptCount = scripts.length;
  assert.strictEqual(await context.prsLoadXlsxLibrary(), XLSX);
  assert.strictEqual(scripts.length, loadedScriptCount);

  console.log("embedded XLSX helpers and workbook round-trip passed");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
