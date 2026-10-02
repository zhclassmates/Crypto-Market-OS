import { createServerFn } from "@tanstack/react-start";
import { DatabaseSync } from "node:sqlite";
import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

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
}

interface TokenStreak {
  chain: string;
  address: string;
  label: string | null;
  days: number;
  pattern: string;
  upDays: number;
  downDays: number;
  flatDays: number;
  latestClose: string;
  candles: KlineRow[];
}

function calcStreak(candles: KlineRow[]): Omit<TokenStreak, "chain" | "address" | "label" | "candles"> {
  if (candles.length < 2) {
    return {
      days: candles.length,
      pattern: "",
      upDays: 0,
      downDays: 0,
      flatDays: 0,
      latestClose: candles[0]?.close ?? "0",
    };
  }
  const marks: string[] = [];
  for (let i = 1; i < candles.length; i++) {
    const prev = Number(candles[i - 1].close);
    const curr = Number(candles[i].close);
    if (curr > prev) marks.push("+");
    else if (curr < prev) marks.push("-");
    else marks.push("=");
  }
  const run = (target: string) => {
    let c = 0;
    for (let i = marks.length - 1; i >= 0; i--) {
      if (marks[i] !== target) break;
      c++;
    }
    return c;
  };
  return {
    days: candles.length,
    pattern: marks.join(""),
    upDays: run("+"),
    downDays: run("-"),
    flatDays: run("="),
    latestClose: candles[candles.length - 1].close,
  };
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
    const todayStart = now - (now % 86400);

    // 单条 SQL 决定可见集合：tokens JOIN 已收盘的日 K（ts < 今日 UTC 0 点）。
    // INNER JOIN + WHERE 天然排除"只有今日未收盘 K"的新币，应用层不再做成员过滤。
    const rows = db
      .prepare(
        "SELECT t.chain, t.address, t.symbol, t.name, k.ts, k.open, k.high, k.low, k.close, k.volume " +
          "FROM tokens t JOIN daily_kline k ON k.chain = t.chain AND k.address = t.address " +
          "WHERE k.ts < ? " +
          "ORDER BY t.chain ASC, t.symbol ASC, t.address ASC, k.ts ASC",
      )
      .all(todayStart) as unknown as (KlineRow & { symbol: string | null; name: string | null })[];

    const groups = new Map<string, { chain: string; address: string; label: string | null; candles: KlineRow[] }>();
    for (const r of rows) {
      const key = `${r.chain}:${r.address}`;
      let g = groups.get(key);
      if (!g) {
        g = { chain: r.chain, address: r.address, label: r.symbol ?? r.name, candles: [] };
        groups.set(key, g);
      }
      g.candles.push({ chain: r.chain, address: r.address, ts: r.ts, open: r.open, high: r.high, low: r.low, close: r.close, volume: r.volume });
    }

    const tokens: TokenStreak[] = [];
    for (const g of groups.values()) {
      const streak = calcStreak(g.candles);
      tokens.push({ chain: g.chain, address: g.address, label: g.label, ...streak, candles: g.candles });
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
