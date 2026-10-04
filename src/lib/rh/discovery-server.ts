import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { DatabaseSync } from "node:sqlite";
import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { sanitizeRules } from "./alerts.ts";
import { buildDiscovery, buildTokenDetail, type DiscoveryResult, type TokenDetail } from "./discovery-core.ts";

export type { DiscoveryRow, DiscoveryResult, TokenDetail, CandleOut } from "./discovery-core.ts";

// 与 market-server 相同：RH_MARKET_DB 只用于离线验证。
const DB_PATH = process.env.RH_MARKET_DB || join(
  dirname(fileURLToPath(import.meta.url)),
  "../../../rh_v2/market.sqlite",
);

function openReadDb(): DatabaseSync {
  const db = new DatabaseSync(DB_PATH, { readOnly: true });
  db.exec("PRAGMA busy_timeout=10000");
  return db;
}

type Fail = { ok: false; error: string };

/** 爆款发现 + 告警评估。规则由前端传入，只在服务端读库计算；不请求 GMGN。 */
export const fetchDiscovery = createServerFn({ method: "POST" })
  .validator(z.object({ rules: z.unknown().optional() }))
  .handler(async ({ data }): Promise<DiscoveryResult | Fail> => {
    try {
      if (!existsSync(DB_PATH)) return { ok: false, error: "数据库不存在，先跑采集器" };
      const db = openReadDb();
      try {
        return buildDiscovery(db, Math.floor(Date.now() / 1000), sanitizeRules(data.rules ?? []));
      } finally {
        db.close();
      }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) };
    }
  });

export const fetchTokenDetail = createServerFn({ method: "POST" })
  .validator(z.object({ chain: z.string().min(1).max(32), address: z.string().min(1).max(128) }))
  .handler(async ({ data }): Promise<TokenDetail | Fail> => {
    try {
      if (!existsSync(DB_PATH)) return { ok: false, error: "数据库不存在，先跑采集器" };
      const db = openReadDb();
      try {
        const out = buildTokenDetail(db, data.chain, data.address, Math.floor(Date.now() / 1000));
        return out ?? { ok: false, error: "库里没有这个代币" };
      } finally {
        db.close();
      }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) };
    }
  });
