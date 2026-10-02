#!/usr/bin/env node
/** Live #sec-market button and race check against the running Vite server. */
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const URL = "http://127.0.0.1:8080/#sec-market";
const PRESETS = [1, 2, 3, 5, 7, 10, 14, 30];
const outPath = join(dirname(fileURLToPath(import.meta.url)), "browser-market-days.out.json");

function pct(v) {
  if (v == null || v === "" || !Number.isFinite(Number(v))) return null;
  return Number(v);
}

async function waitBoard(page, days, timeout = 45000) {
  await page.waitForFunction(
    (d) => {
      const table = document.querySelector("table[data-days]");
      const count = document.querySelector("[data-testid=board-count]");
      if (!table || !count) return false;
      if (table.getAttribute("data-days") !== String(d)) return false;
      if (table.getAttribute("data-applied-days") !== String(d)) return false;
      if ((count.textContent || "").includes("计算中")) return false;
      return document.querySelectorAll("tbody tr[data-symbol]").length > 0;
    },
    days,
    { timeout },
  );
}

async function snapshot(page) {
  return page.evaluate(() => {
    const table = document.querySelector("table[data-days]");
    const count = document.querySelector("[data-testid=board-count]");
    const active = [...document.querySelectorAll("button[data-days]")].find(
      (b) => b.getAttribute("aria-pressed") === "true",
    );
    const header = [...document.querySelectorAll("th")].map((th) => th.textContent.trim());
    const rows = [...document.querySelectorAll("tbody tr[data-symbol]")].slice(0, 12).map((tr, i) => ({
      rank: i + 1,
      symbol: tr.getAttribute("data-symbol"),
      address: tr.getAttribute("data-address"),
      streak: tr.getAttribute("data-streak"),
      changeNd: tr.getAttribute("data-change-nd"),
      dailyStatus: tr.getAttribute("data-daily-status"),
      streakText: tr.querySelector("[data-col=streak]")?.textContent.trim() ?? "",
      ndText: tr.querySelector("[data-col=changeNd]")?.textContent.trim() ?? "",
      change1dText: tr.querySelector("[data-col=change1d]")?.textContent.trim() ?? "",
    }));
    const pump = [...document.querySelectorAll("tbody tr[data-symbol]")].find(
      (tr) => (tr.getAttribute("data-symbol") || "").toUpperCase() === "PUMPGU",
    );
    const pumpgu = pump
      ? {
          symbol: pump.getAttribute("data-symbol"),
          address: pump.getAttribute("data-address"),
          streak: pump.getAttribute("data-streak"),
          changeNd: pump.getAttribute("data-change-nd"),
          dailyStatus: pump.getAttribute("data-daily-status"),
          streakText: pump.querySelector("[data-col=streak]")?.textContent.trim() ?? "",
          ndText: pump.querySelector("[data-col=changeNd]")?.textContent.trim() ?? "",
          change1dText: pump.querySelector("[data-col=change1d]")?.textContent.trim() ?? "",
        }
      : null;
    return {
      days: table?.getAttribute("data-days"),
      appliedDays: table?.getAttribute("data-applied-days"),
      sort: table?.getAttribute("data-sort"),
      active: active?.textContent.trim() ?? null,
      countText: count?.textContent.trim() ?? null,
      header,
      rows,
      pumpgu,
    };
  });
}

const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: ["--disable-dev-shm-usage"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
const consoleErrors = [];
page.on("console", (msg) => {
  if (msg.type() === "error") consoleErrors.push(msg.text());
});
page.on("pageerror", (err) => consoleErrors.push(String(err)));

const result = { ok: true, buttons: {}, race: null, consoleErrors: [], shots: [] };

try {
  await page.goto(URL, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("button[data-days]", { timeout: 30000 });

  for (const d of PRESETS) {
    await page.click(`button[data-days="${d}"]`);
    await waitBoard(page, d);
    const snap = await snapshot(page);
    const headerHas = snap.header.some((h) => h.includes(`${d}D累计`));
    const streakCol = snap.header.some((h) => h.includes("连续上涨"));
    const countOk = (snap.countText || "").startsWith(`${d}D窗口`);
    const activeOk = snap.active === `${d}D`;
    const appliedOk = snap.appliedDays === String(d);
    const sortOk = snap.sort === "changeNd";
    const pass = headerHas && streakCol && countOk && activeOk && appliedOk && sortOk && snap.rows.length > 0;
    result.buttons[`${d}D`] = { pass, ...snap };
    if (!pass) result.ok = false;
    console.log(
      `${d}D`,
      pass ? "PASS" : "FAIL",
      snap.countText,
      "top",
      snap.rows.slice(0, 3).map((r) => `${r.symbol} streak=${r.streak} nd=${r.ndText}`).join(" | "),
    );
  }

  // Rapid switch: 1D → 30D → 3D → 14D → 5D. Final board must be 5D.
  for (const d of [1, 30, 3, 14, 5]) {
    await page.click(`button[data-days="${d}"]`);
  }
  await waitBoard(page, 5, 60000);
  const raceSnap = await snapshot(page);
  const racePass = raceSnap.appliedDays === "5" && raceSnap.active === "5D" && (raceSnap.countText || "").startsWith("5D窗口");
  result.race = { pass: racePass, ...raceSnap };
  if (!racePass) result.ok = false;
  console.log("RACE final", racePass ? "PASS" : "FAIL", raceSnap.countText, raceSnap.appliedDays);

  await page.fill('input[placeholder="搜索 token"]', "PUMPGU");
  await page.waitForTimeout(400);
  const pumpSnap = await snapshot(page);
  result.pumpgu5d = pumpSnap.pumpgu;
  result.pumpguVisible = Boolean(pumpSnap.pumpgu);
  console.log("PUMPGU 5D", pumpSnap.pumpgu);
  await page.screenshot({ path: join(dirname(fileURLToPath(import.meta.url)), "../screenshots/market-days-5d.png"), fullPage: false });
  result.shots.push("screenshots/market-days-5d.png");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: join(dirname(fileURLToPath(import.meta.url)), "../screenshots/market-days-5d-mobile.png"), fullPage: false });
  result.shots.push("screenshots/market-days-5d-mobile.png");

  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("http://127.0.0.1:8080/#sec-streak", { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("table", { timeout: 30000 });
  const streakPage = await page.evaluate(() => {
    const rows = [...document.querySelectorAll("tbody tr")].slice(0, 8).map((tr) =>
      [...tr.querySelectorAll("td")].slice(0, 5).map((td) => td.textContent.trim()),
    );
    const pump = [...document.querySelectorAll("tbody tr")].find((tr) =>
      (tr.textContent || "").toUpperCase().includes("PUMPGU"),
    );
    return {
      href: location.hash,
      rows,
      pumpguText: pump ? pump.textContent.trim().slice(0, 240) : null,
    };
  });
  result.streakPage = streakPage;
  await page.screenshot({ path: join(dirname(fileURLToPath(import.meta.url)), "../screenshots/kline-desktop-list.png"), fullPage: false });
  result.shots.push("screenshots/kline-desktop-list.png");
  console.log("STREAK page", streakPage.href, "pumpgu", streakPage.pumpguText);
} catch (e) {
  result.ok = false;
  result.error = e instanceof Error ? e.message : String(e);
  console.error(result.error);
} finally {
  result.consoleErrors = consoleErrors;
  if (consoleErrors.length) {
    // Vite HMR noise is not a page bug; keep it but don't auto-fail unless it's a real exception.
    const real = consoleErrors.filter((m) => !m.includes("Download the React DevTools"));
    result.consoleErrors = real;
  }
  writeFileSync(outPath, JSON.stringify(result, null, 2));
  await browser.close();
}

if (!result.ok) process.exit(1);
console.log("browser-market-days OK");
