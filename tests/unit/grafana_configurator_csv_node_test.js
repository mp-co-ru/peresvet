const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const dashboardPath = process.argv[2];
const dashboard = JSON.parse(fs.readFileSync(dashboardPath, "utf8"));
const source = dashboard.panels[0].options.onRender;
const start = source.indexOf(
  'var Ze="",et={},tt="",rt={},prsTagDataExportSnapshot='
);
const end = source.indexOf(",prsSwitchTagDataTab=", start);
assert(start >= 0 && end > start, "CSV helper block was not found");

const context = {
  URL,
  Blob,
  TextEncoder,
  setTimeout,
  clearTimeout,
  console,
  Promise,
  n() {
    return {
      empty() {
        return this;
      },
      text() {
        return "";
      },
      val() {
        return "";
      },
      append() {
        return this;
      },
      appendTo() {
        return this;
      },
    };
  },
  document: {
    createElement() {
      return { click() {}, remove() {} };
    },
    body: { appendChild() {} },
  },
  window: {},
  showAlert() {},
  __prsConfiguratorGetEl() {
    return { disabled: false };
  },
  fetch: null,
  prsMergeIntegParamsIntoTagDataItem() {},
};
context.window = context;
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);

const formatted = context.prsBuildTagDataCsv({
  tagName: "Скорость",
  tagId: "id-1",
  requestLine: "GET http://host/v1/data/?tagId=id-1&format=true",
  url: "http://host/v1/data/?tagId=id-1&format=true",
  params: { tagId: "id-1", format: true, start: "2026-09-27T08:00:00.000Z" },
  points: [
    ["2026-09-27T11:00:00+03:00", 1.5, null],
    ["2026-09-27T11:01:00+03:00", "a,b", 0],
  ],
  timestamp: "2026-09-27T11:02:00.000Z",
});
assert(formatted.charCodeAt(0) === 0xfeff, "CSV must start with a UTF-8 BOM");
const formattedLines = formatted.slice(1).trim().split(/\r\n/);
assert.deepStrictEqual(formattedLines.slice(0, 6), [
  '"name","Скорость"',
  '"id","id-1"',
  '"request","GET http://host/v1/data/?tagId=id-1&format=true"',
  '"tagId","id-1"',
  '"format",true',
  '"start","2026-09-27T08:00:00.000Z"',
]);
assert.strictEqual(formattedLines[6], "x,y,q");
assert.strictEqual(
  formattedLines[7],
  '"2026-09-27T11:00:00+03:00",1.5,'
);
assert.strictEqual(
  formattedLines[8],
  '"2026-09-27T11:01:00+03:00","a,b",0'
);

const raw = context.prsBuildTagDataCsv({
  tagName: "Тег",
  tagId: "id-2",
  requestLine: "GET http://host/v1/data/?tagId=id-2",
  url: "http://host/v1/data/?tagId=id-2",
  params: { tagId: "id-2" },
  points: [[1545288780000000, 4, null]],
  timestamp: "t",
});
assert(
  raw.includes("\r\n1545288780000000,4,\r\n"),
  "timestamps without format must stay integer microseconds"
);
assert(!raw.includes('"1545288780000000"'));

assert.strictEqual(context.prsParseTagSetTimestamp(""), null);
assert.strictEqual(context.prsParseTagSetTimestamp("  "), null);
assert.strictEqual(
  context.prsParseTagSetTimestamp("1545288780000000"),
  1545288780000000
);
assert.strictEqual(context.prsParseTagSetTimestamp("-12"), -12);
assert.strictEqual(
  context.prsParseTagSetTimestamp("2026-09-27T11:00:00+03:00"),
  "2026-09-27T11:00:00+03:00"
);

const picked = new Date(2026, 8, 27, 13, 46, 5);
const pickedText = context.prsFormatLocalDateTime(picked);
assert.strictEqual(pickedText.slice(0, 19), "2026-09-27T13:46:05");
const offsetMin = -picked.getTimezoneOffset();
const offsetSign = offsetMin < 0 ? "-" : "+";
const offsetAbs = Math.abs(offsetMin);
const offsetHh = String(Math.floor(offsetAbs / 60)).padStart(2, "0");
const offsetMm = String(offsetAbs % 60).padStart(2, "0");
assert.strictEqual(pickedText.slice(19), offsetSign + offsetHh + ":" + offsetMm);

const fileName = context.prsTagDataCsvFileName({ tagName: "Насос 1" });
assert.match(
  fileName,
  /^Насос 1 :: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}\.csv$/
);
assert.strictEqual(
  context.prsTagDataCsvFileName({ tagName: "a/b:c" }).split(" :: ")[0],
  "a_b_c"
);
assert.strictEqual(
  context.prsTagDataCsvFileName({ tagName: "   " }).split(" :: ")[0],
  "tag"
);

function assertCoerced(raw, typeCode, expectedOk, expectedValue) {
  const coerced = context.prsCoerceTagSetValue(raw, typeCode);
  assert.strictEqual(coerced.ok, expectedOk);
  if (expectedOk) {
    assert.strictEqual(JSON.stringify(coerced.value), JSON.stringify(expectedValue));
  }
}
assertCoerced("10", 0, true, 10);
assertCoerced("10.0", 0, true, 10);
assertCoerced("10.5", 0, false);
assertCoerced("10.5", 1, true, 10.5);
assertCoerced("нет", 1, false);
assertCoerced("1", 2, true, "1");
assert.strictEqual(typeof context.prsCoerceTagSetValue("1", 2).value, "string");
assertCoerced('{"a":1}', 4, true, { a: 1 });
assertCoerced("не json", 4, false);
assertCoerced("текст", 5, true, "текст");

const timeStart = source.indexOf("prsParseLooseDateTime=function");
const timeEnd = source.indexOf(",formTagDataPanels=", timeStart);
assert(timeStart >= 0 && timeEnd > timeStart, "start/finish parser was not found");
vm.runInContext(source.slice(timeStart, timeEnd), context);

assert.strictEqual(context.prsTagGetTimeQueryValue(""), null);
assert.strictEqual(context.prsTagGetTimeQueryValue("   "), null);
assert.strictEqual(
  context.prsTagGetTimeQueryValue("1790519656001151"),
  "1790519656001151"
);
assert.strictEqual(
  context.prsTagGetTimeQueryValue("2026-09-25T10:07:38.183+03:00"),
  new Date("2026-09-25T10:07:38.183+03:00").toISOString()
);
assert.strictEqual(
  context.prsTagGetTimeQueryValue("25.09.2026, 10:00:00"),
  new Date(2026, 8, 25, 10, 0, 0).toISOString()
);
const copied = "2026-09-25T10:00:00+03:00";
assert.strictEqual(
  context.prsTagGetTimeQueryValue(copied),
  context.prsTagGetTimeQueryValue(copied)
);
