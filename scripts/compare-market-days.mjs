#!/usr/bin/env node
/** Dump backend-equivalent rank from SQLite + streak.ts (no serverFn). */
import { DatabaseSync } from "node:sqlite";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  displayCreated,
  officialDailyMetrics,
  parseDays,
} from "../src/lib/rh/streak.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const db = new DatabaseSync(join(root, "rh_v2/market.sqlite"), { open: true });
db.exec("PRAGMA busy_timeout=10000");
const now = Math.floor(Date.now() / 1000);
const days = parseDays(process.argv[2] ?? 5);
const want = (process.argv[3] || "PUMPGU,STOCKER,SAPLING,PRIORS,UDR,PARLEY,SPIKE,ATLAS,DRMR,CINEMA,HEARTH")
  .split(",")
  .map((s) => s.trim().toUpperCase())
  .filter(Boolean);

const cols = db.prepare("PRAGMA table_info(daily_kline)").all();
const hasFetched = cols.some((c) => c.name === "fetched_at");
const barSql = hasFetched
  ? "SELECT chain, address, ts, high, close, fetched_at, finalized_at FROM daily_kline"
  : "SELECT chain, address, ts, high, close, NULL AS fetched_at, NULL AS finalized_at FROM daily_kline";

const bars = new Map();
for (const row of db.prepare(barSql).all()) {
  const key = `${row.chain}:${row.address}`;
  const list = bars.get(key) ?? [];
  list.push({
    ts: row.ts,
    high: Number(row.high),
    close: Number(row.close),
    fetchedAt: row.fetched_at ?? null,
    finalizedAt: row.finalized_at ?? null,
  });
  bars.set(key, list);
}

const tokens = db.prepare(
  `SELECT r.chain, r.address, COALESCE(t.symbol, r.symbol) AS symbol,
          COALESCE(t.token_created_at, r.token_created_at) AS token_created_at,
          t.pair_created_at, t.kline_fetched_at
   FROM token_registry r
   LEFT JOIN tokens t ON t.chain = r.chain AND t.address = r.address`,
).all();

const rows = [];
for (const t of tokens) {
  const created = displayCreated(t.token_created_at ?? null, t.pair_created_at ?? null);
  const tokenBars = bars.get(`${t.chain}:${t.address}`) ?? [];
  const metrics = officialDailyMetrics(tokenBars, now, created.at, days);
  rows.push({
    symbol: t.symbol,
    chain: t.chain,
    address: t.address,
    changeNd: metrics.changeNd,
    streak: metrics.streak,
    change1d: metrics.change1d,
    closed: metrics.closedCount,
    lastStatus: metrics.lastStatus,
    qualityFlags: metrics.qualityFlags,
  });
}
db.close();

const ranked = rows
  .filter((r) => r.changeNd != null && Number.isFinite(r.changeNd))
  .sort((a, b) => b.changeNd - a.changeNd);

console.log(JSON.stringify({
  now,
  days,
  eligible: ranked.length,
  top10: ranked.slice(0, 10),
  named: rows.filter((r) => r.symbol && want.includes(String(r.symbol).toUpperCase())),
}, null, 2));
