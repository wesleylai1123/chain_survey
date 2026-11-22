import assert from "node:assert/strict";
import { mkdir, readFile } from "node:fs/promises";
import { join } from "node:path";

const { chromium } = await import(process.env.CHAIN_SURVEY_PLAYWRIGHT || "playwright");
const browser = await chromium.launch(process.env.CHAIN_SURVEY_BROWSER
  ? { executablePath: process.env.CHAIN_SURVEY_BROWSER }
  : {});
const url = process.env.CHAIN_SURVEY_PREVIEW || "http://127.0.0.1:8765";
const directory = process.env.CHAIN_SURVEY_SCREENSHOTS || "artifacts/research-web";
const baseline = ["pcb_revenue_yoy", "abf_company_revenue_yoy::3037.TW"];
const issues = [];
await mkdir(directory, { recursive: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 }, acceptDownloads: true });
page.on("pageerror", error => issues.push(String(error)));

async function ready() {
  await page.waitForFunction(() => document.querySelector("#stat-n").textContent.match(/^[1-9]/));
}

function coefficient(x, y) {
  const n = x.length;
  const sum = values => values.reduce((total, value) => total + value, 0);
  const xMean = sum(x) / n;
  const yMean = sum(y) / n;
  const xDiff = x.map(value => value - xMean);
  const yDiff = y.map(value => value - yMean);
  return sum(xDiff.map((value, index) => value * yDiff[index]))
    / Math.sqrt(sum(xDiff.map(value => value ** 2)) * sum(yDiff.map(value => value ** 2)));
}

function ranks(values) {
  return values.map(value => values.filter(other => other < value).length
    + (values.filter(other => other === value).length + 1) / 2);
}

try {
  await page.goto(url);
  await ready();
  await page.waitForSelector("#main-plot .scatterlayer .trace");
  assert.equal(await page.locator("#main-plot .scatterlayer .trace").count(), 2);
  assert.equal(await page.locator("#pair-x").inputValue(), baseline[0]);
  await page.screenshot({ path: join(directory, "desktop.png"), fullPage: true });

  const rows = Array.from({ length: 20 }, (_, index) => [3, 15].map(day => {
    const date = new Date(Date.UTC(2024, index, day)).toISOString().slice(0, 10);
    return `${date},${50 + index * 2 + (index % 4) * 7 + day}`;
  })).flat();
  await page.locator("#open-import").click();
  await page.locator("#import-file").setInputFiles({
    name: "local-prices.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("date,收盤價\n" + rows.join("\n")),
  });
  await page.locator('#import-columns input[value="收盤價"]').check();
  await page.locator("#import-frequency").selectOption("D");
  await page.locator("#import-source").fill("Local browser QA data");
  const importResult = page.waitForResponse(response => response.url().endsWith("/api/csv/import"));
  await page.locator("#submit-import").click();
  const imported = await (await importResult).json();
  assert.equal(imported.series.length, 1);
  assert.equal(imported.series[0].frequency, "D");
  const id = imported.series[0].id;
  await page.waitForFunction(value => [...document.querySelector("#pair-x").options].some(item => item.value === value), id);

  await page.locator("#pair-x").selectOption(id);
  await page.locator("#pair-y").selectOption(baseline[1]);
  await page.locator("#lag").fill("1");
  await page.locator("#aggregation").selectOption("mean");
  const analysisResponse = page.waitForResponse(response => response.url().endsWith("/api/analyze")
    && response.request().postDataJSON().x === id && response.request().postDataJSON().lag === 1);
  await page.locator("#run-analysis").click();
  const analysis = await (await analysisResponse).json();
  assert.equal(analysis.n, 20);
  assert.equal(analysis.samples[0].x_date, "2024-01-31");
  assert.equal(analysis.samples[0].y_date, "2024-02-29");
  assert.equal(analysis.samples[0].x, 59);

  await page.locator("#tab-samples").click();
  await page.locator("#sample-rows tr").first().waitFor();
  assert.equal(await page.locator("#stat-n").textContent(), "20");
  const downloadEvent = page.waitForEvent("download");
  await page.locator("#export-samples").click();
  const download = await downloadEvent;
  const output = join(directory, "qa-samples.csv");
  await download.saveAs(output);
  const exported = await readFile(output, "utf8");
  const [header, ...exportedRows] = exported.replace(/^\uFEFF/, "").trim().split(/\r?\n/);
  const columns = header.split(",").map(value => value.replaceAll('"', ""));
  const first = exportedRows[0].split(",").map(value => value.replaceAll('"', ""));
  assert.equal(exportedRows.length, 20);
  assert.equal(first[columns.indexOf("x_date")], "2024-01-31");
  assert.equal(first[columns.indexOf("y_date")], "2024-02-29");
  assert.equal(first[columns.indexOf("x_source")], "Local browser QA data");
  assert.equal(first[columns.indexOf("x_filename")], "local-prices.csv");
  const values = name => exportedRows.map(row => Number(row.split(",")[columns.indexOf(name)].replaceAll('"', "")));
  const x = values("x");
  const y = values("y");
  assert.equal(x[0], 59);
  assert.ok(Math.abs(analysis.pearson - coefficient(x, y)) < 1e-10);
  assert.ok(Math.abs(analysis.spearman - coefficient(ranks(x), ranks(y))) < 1e-10);

  await page.locator("#tab-scatter").click();
  await page.waitForSelector("#scatter-plot .scatterlayer .trace");
  await page.locator("#tab-lags").click();
  await page.waitForSelector("#lag-rows tr");
  assert.equal(await page.locator("#lag-rows tr").count(), 13);

  await page.locator("#save-group").click();
  await page.locator("#group-name").fill("本機樣本研究");
  await page.locator("#submit-group").click();
  await page.reload();
  await ready();
  await page.locator("#open-groups").click();
  await page.locator("#group-list").getByRole("button", { name: "套用群組 本機樣本研究" }).click();
  await page.waitForFunction(value => document.querySelector("#pair-x").value === value, id);
  assert.equal(await page.locator("#lag").inputValue(), "1");
  assert.equal(await page.locator("#aggregation").inputValue(), "mean");

  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 1 });
  await mobile.goto(url);
  await mobile.waitForSelector("#main-plot .scatterlayer .trace");
  assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth), 390);
  await mobile.screenshot({ path: join(directory, "mobile.png"), fullPage: true });
  assert.deepEqual(issues, []);
  console.log("RESEARCH_WEB_UI_OK", { samples: analysis.n, pearson: analysis.pearson, spearman: analysis.spearman });
} finally {
  await browser.close();
}
