/** 一轮真拉数。不写假币。某个源失败就记在 log 里，别的源继续。 */

const UA = { Accept: "application/json", "User-Agent": "rhv2-collector/0.2" };
const QUOTES = new Set(["WETH", "ETH", "USDC", "USDT", "USDG", "DAI", "USDE", "WBTC", "CBBTC", "U", "USD1"]);

export type RawTok = {
  address: string;
  symbol: string;
  name: string;
  price: number | null;
  mcap: number | null;
  liq: number | null;
  volH1: number | null;
  volH6: number | null;
  volH24: number | null;
  buysH1: number | null;
  sellsH1: number | null;
  buysH6: number | null;
  sellsH6: number | null;
  buysH24: number | null;
  sellsH24: number | null;
  pcH6: number | null;
  pcH24: number | null;
  buyersH1: number | null;
  buyersH24: number | null;
  pairCreated: number | null;
  holders: number | null;
  fromDex: boolean;
};

export type CollectLog = {
  secs: number;
  universe: string;
  gt: string;
  rhchain: string;
  dex: string;
  alpha: string;
  queried: number;
  got: number;
  obs: number;
};

export type CollectOk = {
  ok: true;
  ts: number;
  log: CollectLog;
  tokens: RawTok[];
  alpha: string[];
};

export type CollectFail = { ok: false; error: string; log?: Partial<CollectLog> };

function n(x: unknown): number | null {
  if (typeof x === "number" && Number.isFinite(x)) return x;
  if (typeof x === "string" && x.trim() && Number.isFinite(Number(x))) return Number(x);
  return null;
}

async function pull(url: string, ms = 18000): Promise<unknown> {
  const res = await fetch(url, { headers: UA, signal: AbortSignal.timeout(ms) });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

async function pullRetry(url: string): Promise<unknown> {
  try {
    return await pull(url);
  } catch (e) {
    if (e instanceof Error && (e.message === "429" || e.name === "TimeoutError")) {
      await new Promise((r) => setTimeout(r, 7000));
      return pull(url);
    }
    throw e;
  }
}

function blank(address: string, symbol: string, name: string): RawTok {
  return {
    address,
    symbol,
    name,
    price: null,
    mcap: null,
    liq: null,
    volH1: null,
    volH6: null,
    volH24: null,
    buysH1: null,
    sellsH1: null,
    buysH6: null,
    sellsH6: null,
    buysH24: null,
    sellsH24: null,
    pcH6: null,
    pcH24: null,
    buyersH1: null,
    buyersH24: null,
    pairCreated: null,
    holders: null,
    fromDex: false,
  };
}

type GtPool = {
  attributes?: {
    address?: string;
    name?: string;
    reserve_in_usd?: string;
    fdv_usd?: string;
    market_cap_usd?: string;
    volume_usd?: Record<string, string>;
    price_change_percentage?: Record<string, string>;
    transactions?: Record<string, { buys?: number; sells?: number; buyers?: number; sellers?: number }>;
    pool_created_at?: string;
    base_token_price_usd?: string;
  };
  relationships?: {
    base_token?: { data?: { id?: string } };
    quote_token?: { data?: { id?: string } };
  };
};

export function parseGt(body: unknown): RawTok[] {
  const res = body as { data?: GtPool[]; included?: { id: string; attributes?: { symbol?: string; name?: string; address?: string } }[] };
  const inc = new Map((res.included ?? []).map((x) => [x.id, x.attributes ?? {}]));
  const out: RawTok[] = [];
  for (const d of res.data ?? []) {
    const rel = d.relationships ?? {};
    let bid = rel.base_token?.data?.id ?? "";
    const qid = rel.quote_token?.data?.id ?? "";
    let b = inc.get(bid) ?? {};
    const q = inc.get(qid) ?? {};
    if (QUOTES.has((b.symbol ?? "").toUpperCase()) && !QUOTES.has((q.symbol ?? "").toUpperCase())) {
      b = q;
      bid = qid;
    }
    const sym = (b.symbol ?? "").toUpperCase();
    if (!bid || QUOTES.has(sym)) continue;
    const address = (b.address || bid.split("_").pop() || "").toLowerCase();
    if (!address.startsWith("0x") || address.length !== 42) continue;
    const a = d.attributes ?? {};
    const vol = a.volume_usd ?? {};
    const pc = a.price_change_percentage ?? {};
    const tx = a.transactions ?? {};
    const h1 = tx.h1 ?? {};
    const h24 = tx.h24 ?? {};
    const row = blank(address, b.symbol || sym, b.name || sym);
    row.price = n(a.base_token_price_usd);
    row.mcap = n(a.market_cap_usd) ?? n(a.fdv_usd);
    row.liq = n(a.reserve_in_usd);
    row.volH1 = n(vol.h1);
    row.volH6 = n(vol.h6);
    row.volH24 = n(vol.h24);
    row.pcH6 = n(pc.h6);
    row.pcH24 = n(pc.h24);
    row.buysH1 = h1.buys ?? null;
    row.sellsH1 = h1.sells ?? null;
    row.buysH24 = h24.buys ?? null;
    row.sellsH24 = h24.sells ?? null;
    row.buyersH1 = h1.buyers ?? null;
    row.buyersH24 = h24.buyers ?? null;
    row.pairCreated = a.pool_created_at ? Math.floor(Date.parse(a.pool_created_at) / 1000) : null;
    out.push(row);
  }
  return out;
}

type ChainTok = {
  symbol?: string;
  name?: string;
  address?: string;
  price?: number;
  mcap?: number;
  volume24h?: number;
  liq?: number;
  chg24h?: number;
  holders?: number | null;
  vol1h?: number;
  vol6h?: number;
  buys24h?: number;
  sells24h?: number;
  buys1h?: number;
  sells1h?: number;
  chg1h?: number;
  chg6h?: number;
  pairAt?: number;
};

function fromChain(t: ChainTok): RawTok | null {
  const address = (t.address || "").toLowerCase();
  if (!address.startsWith("0x") || address.length !== 42) return null;
  const sym = (t.symbol || "").toUpperCase();
  if (!sym || QUOTES.has(sym)) return null;
  const row = blank(address, t.symbol || sym, t.name || sym);
  row.price = n(t.price);
  row.mcap = n(t.mcap);
  row.liq = n(t.liq);
  row.volH1 = n(t.vol1h);
  row.volH6 = n(t.vol6h);
  row.volH24 = n(t.volume24h);
  row.buysH1 = n(t.buys1h);
  row.sellsH1 = n(t.sells1h);
  row.buysH24 = n(t.buys24h);
  row.sellsH24 = n(t.sells24h);
  row.pcH6 = n(t.chg6h);
  row.pcH24 = n(t.chg24h);
  row.holders = n(t.holders);
  row.pairCreated = t.pairAt ? Math.floor(t.pairAt / 1000) : null;
  return row;
}

type DsPair = {
  baseToken?: { address?: string; symbol?: string; name?: string };
  priceUsd?: string;
  marketCap?: number | string;
  fdv?: number | string;
  liquidity?: { usd?: number | string };
  volume?: { h1?: number | string; h6?: number | string; h24?: number | string };
  txns?: Record<string, { buys?: number; sells?: number }>;
  priceChange?: { h1?: number; h6?: number; h24?: number };
  pairCreatedAt?: number;
};

function overlayDex(map: Map<string, RawTok>, pairs: DsPair[]) {
  const grouped = new Map<string, DsPair[]>();
  for (const p of pairs) {
    const address = (p.baseToken?.address || "").toLowerCase();
    if (!address.startsWith("0x")) continue;
    const arr = grouped.get(address) ?? [];
    arr.push(p);
    grouped.set(address, arr);
  }
  let got = 0;
  for (const [address, list] of grouped) {
    const top = list.reduce((a, b) => ((n(a.liquidity?.usd) ?? 0) >= (n(b.liquidity?.usd) ?? 0) ? a : b));
    const prev = map.get(address) ?? blank(address, top.baseToken?.symbol || address.slice(0, 6), top.baseToken?.name || "");
    const sum = (pick: (p: DsPair) => number | null) => list.reduce((a, p) => a + (pick(p) ?? 0), 0);
    const tx = (w: string, side: "buys" | "sells") => list.reduce((a, p) => a + (p.txns?.[w]?.[side] ?? 0), 0);
    prev.symbol = top.baseToken?.symbol || prev.symbol;
    prev.name = top.baseToken?.name || prev.name;
    prev.price = n(top.priceUsd) ?? prev.price;
    prev.mcap = n(top.marketCap) ?? n(top.fdv) ?? prev.mcap;
    prev.liq = sum((p) => n(p.liquidity?.usd)) || prev.liq;
    prev.volH1 = sum((p) => n(p.volume?.h1));
    prev.volH6 = sum((p) => n(p.volume?.h6));
    prev.volH24 = sum((p) => n(p.volume?.h24));
    prev.buysH1 = tx("h1", "buys");
    prev.sellsH1 = tx("h1", "sells");
    prev.buysH6 = tx("h6", "buys");
    prev.sellsH6 = tx("h6", "sells");
    prev.buysH24 = tx("h24", "buys");
    prev.sellsH24 = tx("h24", "sells");
    prev.pcH6 = n(top.priceChange?.h6) ?? prev.pcH6;
    prev.pcH24 = n(top.priceChange?.h24) ?? prev.pcH24;
    const created = list.map((p) => p.pairCreatedAt).filter((x): x is number => typeof x === "number");
    if (created.length) prev.pairCreated = Math.floor(Math.min(...created) / 1000);
    prev.fromDex = true;
    map.set(address, prev);
    got += 1;
  }
  return got;
}

function alphaAddrs(body: unknown): string[] {
  const rows = ((body as { data?: { chainId?: string | number; contractAddress?: string; offline?: boolean; offsell?: boolean }[] }).data ?? []);
  const out: string[] = [];
  for (const t of rows) {
    if (String(t.chainId ?? "") !== "4663" || t.offline || t.offsell) continue;
    const a = (t.contractAddress || "").toLowerCase();
    if (a.startsWith("0x") && a.length === 42) out.push(a);
  }
  return out;
}

export async function collectNow(): Promise<CollectOk | CollectFail> {
  const t0 = Date.now();
  const log: CollectLog = {
    secs: 0,
    universe: "",
    gt: "",
    rhchain: "",
    dex: "",
    alpha: "",
    queried: 0,
    got: 0,
    obs: 0,
  };
  const [gtR, chainR, alphaR] = await Promise.allSettled([
    pullRetry("https://api.geckoterminal.com/api/v2/networks/robinhood/pools?page=1&sort=h24_volume_usd_desc&include=base_token,quote_token"),
    pull("https://ru7.one/api/rhchain"),
    pull("https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list"),
  ]);

  const map = new Map<string, RawTok>();
  if (gtR.status === "fulfilled") {
    const rows = parseGt(gtR.value);
    for (const r of rows) map.set(r.address, r);
    log.gt = `GeckoTerminal ${rows.length} 个池`;
  } else {
    log.gt = `GeckoTerminal 失败 ${gtR.reason instanceof Error ? gtR.reason.message : ""}`.trim();
  }

  if (chainR.status === "fulfilled") {
    const body = chainR.value as { memes?: ChainTok[]; stocks?: ChainTok[]; others?: ChainTok[] };
    let n = 0;
    for (const t of [...(body.memes ?? []), ...(body.others ?? []), ...(body.stocks ?? [])]) {
      const row = fromChain(t);
      if (!row) continue;
      n += 1;
      const prev = map.get(row.address);
      if (!prev) map.set(row.address, row);
      else {
        // GT 没有 6h 成交笔数时，用这条上已经带的窗口补缺，不覆盖已有数字
        prev.volH1 ??= row.volH1;
        prev.volH6 ??= row.volH6;
        prev.volH24 ??= row.volH24;
        prev.liq ??= row.liq;
        prev.mcap ??= row.mcap;
        prev.price ??= row.price;
        prev.pcH6 ??= row.pcH6;
        prev.pcH24 ??= row.pcH24;
        prev.buysH1 ??= row.buysH1;
        prev.sellsH1 ??= row.sellsH1;
        prev.buysH24 ??= row.buysH24;
        prev.sellsH24 ??= row.sellsH24;
        prev.holders ??= row.holders;
        prev.pairCreated ??= row.pairCreated;
        if (!prev.name) prev.name = row.name;
      }
    }
    log.rhchain = `链上表 ${n} 个`;
  } else {
    log.rhchain = `链上表失败 ${chainR.reason instanceof Error ? chainR.reason.message : ""}`.trim();
  }

  const alpha = alphaR.status === "fulfilled" ? alphaAddrs(alphaR.value) : [];
  log.alpha = alphaR.status === "fulfilled" ? `币安 Alpha ${alpha.length} 个 RH 合约` : `币安 Alpha 失败 ${alphaR.reason instanceof Error ? alphaR.reason.message : ""}`.trim();

  if (!map.size) {
    log.secs = Math.round((Date.now() - t0) / 100) / 10;
    return { ok: false, error: "这一轮一个币都没拉到", log };
  }

  const ranked = [...map.values()].sort((a, b) => (b.volH24 ?? 0) - (a.volH24 ?? 0));
  const batch = ranked.slice(0, 30).map((t) => t.address);
  log.queried = batch.length;
  try {
    const ds = await pullRetry(`https://api.dexscreener.com/tokens/v1/robinhood/${batch.join(",")}`);
    const pairs = Array.isArray(ds) ? (ds as DsPair[]) : [];
    log.got = overlayDex(map, pairs);
    log.dex = `DexScreener 直接拉到 ${log.got}/${batch.length}`;
  } catch (e) {
    log.dex = `DexScreener 失败 ${e instanceof Error ? e.message : ""}`.trim();
    log.got = 0;
  }

  const obs = [...map.values()].filter((t) => (t.liq ?? 0) >= 25_000 && (t.volH24 ?? 0) >= 20_000);
  obs.sort((a, b) => (b.volH24 ?? 0) - (a.volH24 ?? 0));
  log.obs = obs.length;
  log.universe = `${map.size} 个币里，观察池 ${obs.length} 个（池深≥$25k 且 24h 量≥$20k）`;
  log.secs = Math.round((Date.now() - t0) / 100) / 10;
  return { ok: true, ts: Math.floor(Date.now() / 1000), log, tokens: obs.slice(0, 40), alpha };
}
