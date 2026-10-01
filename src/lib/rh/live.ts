import { createServerFn } from "@tanstack/react-start";
import { collectNow } from "@/lib/rh/collect-core";
import type { LadderSnapshot } from "@/lib/rh/types";

export type AlphaHit = { symbol: string; address: string; listingTime: number | null };

export type AlphaRefresh =
  | { ok: true; n: number; fetchedAt: number; tokens: AlphaHit[] }
  | { ok: false; error: string };

/** 币安 Alpha 公开列表里 chainId = 4663（Robinhood 链）的合约。只读，不写库。 */
export const fetchRhAlpha = createServerFn({ method: "GET" }).handler(async (): Promise<AlphaRefresh> => {
  try {
    const res = await fetch(
      "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list",
      { headers: { Accept: "application/json", "User-Agent": "rh-ladder/1.0" } },
    );
    if (!res.ok) return { ok: false, error: `币安返回 ${res.status}` };
    const body = (await res.json()) as {
      data?: { symbol?: string; chainId?: string | number; contractAddress?: string; listingTime?: number; offline?: boolean; offsell?: boolean }[];
    };
    const tokens: AlphaHit[] = [];
    for (const t of body.data ?? []) {
      if (String(t.chainId ?? "") !== "4663") continue;
      if (t.offline || t.offsell) continue;
      const address = (t.contractAddress || "").toLowerCase();
      if (!address.startsWith("0x") || address.length !== 42) continue;
      tokens.push({
        symbol: (t.symbol || "").toUpperCase(),
        address,
        listingTime: typeof t.listingTime === "number" ? t.listingTime : null,
      });
    }
    tokens.sort((a, b) => (b.listingTime ?? 0) - (a.listingTime ?? 0));
    return { ok: true, n: tokens.length, fetchedAt: Date.now(), tokens };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "拉不到币安 Alpha" };
  }
});

export const collect = createServerFn({ method: "GET" }).handler(async () => collectNow());

const KEEP = ["aster", "hl", "bnAlpha", "bnPerp", "bnSpot", "kr", "rhQuoted", "rhSpot"];

export const fetchLadder = createServerFn({ method: "GET" }).handler(async (): Promise<{ ok: true; book: LadderSnapshot } | { ok: false; error: string }> => {
  try {
    const res = await fetch("https://ru7.one/api/ladder", {
      headers: { Accept: "application/json", "User-Agent": "rh-ladder/1.0" },
      signal: AbortSignal.timeout(25000),
    });
    if (!res.ok) return { ok: false, error: `台阶列表 ${res.status}` };
    const d = (await res.json()) as Record<string, unknown>;
    if (!d || d.ok === false) return { ok: false, error: "台阶列表没有数据" };
    const rawTokens = (d.tokens as Record<string, unknown>[]) ?? [];
    const tokens = [];
    for (const t of rawTokens) {
      const reached = (t.reached as Record<string, boolean>) ?? {};
      const advanced = KEEP.some((k) => reached[k]);
      const liq = Number(t.liq) || 0;
      const vol = Number(t.vol24h) || 0;
      if (liq < 20_000 && vol < 8_000 && !advanced) continue;
      const address = String(t.address || "").toLowerCase();
      tokens.push({
        symbol: String(t.symbol || ""),
        address: address.startsWith("0x") ? address : null,
        kind: String(t.kind || "meme"),
        name: String(t.name || t.symbol || ""),
        vol24h: t.vol24h == null ? null : Number(t.vol24h),
        liq: t.liq == null ? null : Number(t.liq),
        mcap: null,
        poolSeenAt: (t.poolSeenAt as string) ?? null,
        krVenue: (t.krVenue as string) ?? null,
        reached: Object.fromEntries(KEEP.map((k) => [k, Boolean(reached[k])])),
      });
    }
    const book = {
      ts: Number(d.ts) || Date.now(),
      coverage: (d.quality as { coverage?: LadderSnapshot["coverage"] })?.coverage ??
        (d.coverage as LadderSnapshot["coverage"]) ?? { active: tokens.length, universe: rawTokens.length },
      kinds: (d.kinds as LadderSnapshot["kinds"]) ?? {},
      rungs: d.rungs,
      funnel: d.funnel,
      gates: d.gates,
      venueRules: d.venueRules,
      listingHistory: d.listingHistory,
      alphaRef: d.alphaRef,
      advancedFeed: d.advancedFeed ?? [],
      ruledOut: Array.isArray(d.ruledOut) ? (d.ruledOut as LadderSnapshot["ruledOut"]).slice(0, 10) : [],
      candidates: Array.isArray(d.candidates) ? (d.candidates as LadderSnapshot["candidates"]).slice(0, 50) : [],
      tokens,
    } as LadderSnapshot;
    return { ok: true, book };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "台阶列表拉失败" };
  }
});
