import { createServerFn } from "@tanstack/react-start";
import { DatabaseSync } from "node:sqlite";
import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  classifyBars,
  displayCreated,
  officialDailyMetrics,
  patternFromFinalized,
  type DailyBar,
  type DailyStatus,
} from "./streak.ts";

const DB_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  "../../../rh_v2/market.sqlite",
);

interface KlineRow {
  chain: string;
  address: string;
  ts: number;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  fetchedAt: number | null;
  finalizedAt: number | null;
  status: DailyStatus;
}

interface TokenStreak {
  chain: string;
  address: string;
  label: string | null;
  days: number;
  pattern: string;
  upDays: number | null;
  downDays: number;
  flatDays: number;
  latestClose: string;
  lastStatus: DailyStatus | null;
  candles: KlineRow[];
}

function dailyKlineSql(db: DatabaseSync): string {
  const cols = db.prepare("PRAGMA table_info(daily_kline)").all() as unknown as { name: string }[];
  const names = new Set(cols.map((c) => c.name));
  if (names.has("fetched_at")) {
    return (
      "SELECT t.chain, t.address, t.symbol, t.name, t.token_created_at, t.pair_created_at, " +
      "k.ts, k.open, k.high, k.low, k.close, k.volume, k.fetched_at, k.finalized_at " +
      "FROM tokens t JOIN daily_kline k ON k.chain = t.chain AND k.address = t.address " +
      "ORDER BY t.chain ASC, t.symbol ASC, t.address ASC, k.ts ASC"
    );
  }
  return (
    "SELECT t.chain, t.address, t.symbol, t.name, t.token_created_at, t.pair_created_at, " +
    "k.ts, k.open, k.high, k.low, k.close, k.volume, NULL AS fetched_at, NULL AS finalized_at " +
    "FROM tokens t JOIN daily_kline k ON k.chain = t.chain AND k.address = t.address " +
    "ORDER BY t.chain ASC, t.symbol ASC, t.address ASC, k.ts ASC"
  );
}

export const fetchKlineBoard = createServerFn({ method: "GET" }).handler(async (): Promise<{
  ok: boolean;
  tokens: TokenStreak[];
  lastRun?: string;
  error?: string;
}> => {
  try {
    if (!existsSync(DB_PATH)) {
      return { ok: false, tokens: [], error: "数据库不存在，先跑 python3 rh_v2/market_run.py once" };
    }
    const db = new DatabaseSync(DB_PATH, { open: true });
    const now = Math.floor(Date.now() / 1000);

    const rows = db.prepare(dailyKlineSql(db)).all() as unknown as {
      chain: string;
      address: string;
      symbol: string | null;
      name: string | null;
      token_created_at: number | null;
      pair_created_at: number | null;
      ts: number;
      open: string;
      high: string;
      low: string;
      close: string;
      volume: string;
      fetched_at: number | null;
      finalized_at: number | null;
    }[];

    const groups = new Map<string, {
      chain: string;
      address: string;
      label: string | null;
      createdAt: number | null;
      candles: DailyBar[];
      raw: KlineRow[];
    }>();
    for (const r of rows) {
      const key = `${r.chain}:${r.address}`;
      let g = groups.get(key);
      if (!g) {
        const created = displayCreated(r.token_created_at ?? null, r.pair_created_at ?? null);
        g = {
          chain: r.chain,
          address: r.address,
          label: r.symbol ?? r.name,
          createdAt: created.at,
          candles: [],
          raw: [],
        };
        groups.set(key, g);
      }
      const bar: DailyBar = {
        ts: r.ts,
        high: Number(r.high),
        close: Number(r.close),
        fetchedAt: r.fetched_at ?? null,
        finalizedAt: r.finalized_at ?? null,
      };
      g.candles.push(bar);
      const classified = classifyBars([bar], now, g.createdAt)[0];
      if (!classified || classified.status !== "FINALIZED") continue;
      g.raw.push({
        chain: r.chain,
        address: r.address,
        ts: r.ts,
        open: r.open,
        high: r.high,
        low: r.low,
        close: r.close,
        volume: r.volume,
        fetchedAt: r.fetched_at ?? null,
        finalizedAt: r.finalized_at ?? null,
        status: classified.status,
      });
    }

    const tokens: TokenStreak[] = [];
    for (const g of groups.values()) {
      if (g.raw.length === 0) continue;
      const official = officialDailyMetrics(g.candles, now, g.createdAt, 1);
      // 尾部 PROVISIONAL 时整行不发布，避免在同一行混入旧 finalized pattern
      // 与 unavailable official streak。新 finalized candle 写入后自动恢复。
      if (official.lastStatus !== "FINALIZED") continue;
      const calendar = classifyBars(g.candles, now, g.createdAt).filter((b) => b.status === "FINALIZED");
      const marks = patternFromFinalized(calendar);
      const latest = g.raw[g.raw.length - 1]!;
      tokens.push({
        chain: g.chain,
        address: g.address,
        label: g.label,
        days: calendar.length,
        pattern: marks.pattern,
        upDays: official.streak,
        downDays: marks.downDays,
        flatDays: marks.flatDays,
        latestClose: latest.close,
        lastStatus: official.lastStatus,
        candles: g.raw,
      });
    }

    const lastRun = db
      .prepare("SELECT v FROM market_meta WHERE k='last_run'")
      .get() as { v: string } | undefined;
    db.close();
    return { ok: true, tokens, lastRun: lastRun?.v };
  } catch (e) {
    return { ok: false, tokens: [], error: e instanceof Error ? e.message : String(e) };
  }
});
