"""数据源。只用标准库，零依赖。每个源单独限速；任何一个源挂掉都不影响其他源落库。"""
import json
import time
import urllib.request
import urllib.error

from config import RPS, CHAIN_DS, CHAIN_GT, BLOCKSCOUT, BLOCKSCOUT_KEY

UA = {"User-Agent": "rhv2-collector/0.1", "Accept": "application/json"}
_last = {}

# 这些是计价资产/稳定币，不当作「币」进宇宙
QUOTE_SYMBOLS = {"WETH", "ETH", "USDC", "USDT", "USDG", "DAI", "USDE", "WBTC", "CBBTC", "U", "USD1"}


def _throttle(src):
    gap = 1.0 / RPS.get(src, 1.0)
    wait = _last.get(src, 0) + gap - time.time()
    if wait > 0:
        time.sleep(wait)
    _last[src] = time.time()


def get_json(src, url, body=None, tries=3, timeout=20):
    headers = dict(UA)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    for i in range(tries):
        _throttle(src)
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:          # 被限速：退避更久
                time.sleep(15 * (i + 1))
                continue
            if e.code == 404:
                return None
            time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def _f(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


# ---------------- DexScreener：全宇宙每小时快照 ----------------

def ds_tokens(addresses):
    """每次最多 30 个地址。返回 {addr: 聚合后的快照 dict}。
    同一币多个池子：量/笔数/池深求和，价格/市值/涨幅取池深最大的那个池子。"""
    out = {}
    addrs = [a.lower() for a in addresses]
    for i in range(0, len(addrs), 30):
        batch = addrs[i:i + 30]
        res = get_json("dexscreener", f"https://api.dexscreener.com/tokens/v1/{CHAIN_DS}/{','.join(batch)}")
        if not isinstance(res, list):
            continue
        for p in res:
            base = (p.get("baseToken") or {}).get("address", "").lower()
            if base not in batch:
                continue
            agg = out.setdefault(base, {"pairs": []})
            agg["pairs"].append(p)
    for addr, agg in out.items():
        pairs = agg.pop("pairs")
        top = max(pairs, key=lambda p: _f((p.get("liquidity") or {}).get("usd")) or 0)
        s = lambda k, w: sum(_f((p.get(k) or {}).get(w)) or 0 for p in pairs)
        tx = lambda w, side: sum(int(((p.get("txns") or {}).get(w) or {}).get(side) or 0) for p in pairs)
        pc = top.get("priceChange") or {}
        agg.update(
            symbol=(top.get("baseToken") or {}).get("symbol"),
            name=(top.get("baseToken") or {}).get("name"),
            top_pool=top.get("pairAddress"), dex=top.get("dexId"),
            pair_created=(min(p["pairCreatedAt"] for p in pairs if p.get("pairCreatedAt")) // 1000
                          if any(p.get("pairCreatedAt") for p in pairs) else None),
            price=_f(top.get("priceUsd")), mcap=_f(top.get("marketCap")), fdv=_f(top.get("fdv")),
            liq=sum(_f((p.get("liquidity") or {}).get("usd")) or 0 for p in pairs),
            vol_h1=s("volume", "h1"), vol_h6=s("volume", "h6"), vol_h24=s("volume", "h24"),
            buys_h1=tx("h1", "buys"), sells_h1=tx("h1", "sells"),
            buys_h6=tx("h6", "buys"), sells_h6=tx("h6", "sells"),
            buys_h24=tx("h24", "buys"), sells_h24=tx("h24", "sells"),
            pc_h1=_f(pc.get("h1")), pc_h6=_f(pc.get("h6")), pc_h24=_f(pc.get("h24")),
            n_pairs=len(pairs),
        )
    return out


# ---------------- GeckoTerminal：发现宇宙 + 观察池独立买家数 ----------------

def _gt_parse_pools(res, source):
    if not res or "data" not in res:
        return []
    inc = {x["id"]: x.get("attributes", {}) for x in res.get("included", []) or []}
    rows = []
    for d in res["data"]:
        a = d.get("attributes", {})
        rel = d.get("relationships", {})
        bid = ((rel.get("base_token") or {}).get("data") or {}).get("id", "")
        qid = ((rel.get("quote_token") or {}).get("data") or {}).get("id", "")
        b, q = inc.get(bid, {}), inc.get(qid, {})
        # 如果 base 是 WETH/稳定币，而 quote 才是新币，就翻过来
        if (b.get("symbol") or "").upper() in QUOTE_SYMBOLS and (q.get("symbol") or "").upper() not in QUOTE_SYMBOLS:
            b, bid = q, qid
        sym = (b.get("symbol") or "").upper()
        if not bid or sym in QUOTE_SYMBOLS:
            continue
        rows.append(dict(
            address=bid.split("_", 1)[-1].lower(), symbol=b.get("symbol"), name=b.get("name"),
            top_pool=a.get("address"),
            dex=((rel.get("dex") or {}).get("data") or {}).get("id"),
            source=source,
        ))
    return rows


def gt_universe(pages):
    rows = []
    for page in range(1, pages + 1):
        res = get_json("geckoterminal",
                       f"https://api.geckoterminal.com/api/v2/networks/{CHAIN_GT}/pools"
                       f"?page={page}&sort=h24_volume_usd_desc&include=base_token,quote_token")
        got = _gt_parse_pools(res, "gt_top")
        if not got:
            break
        rows += got
    res = get_json("geckoterminal",
                   f"https://api.geckoterminal.com/api/v2/networks/{CHAIN_GT}/new_pools"
                   f"?page=1&include=base_token,quote_token")
    rows += _gt_parse_pools(res, "gt_new")
    return rows


def gt_pool_flows(pool_addrs):
    """观察池专用：独立买家/卖家地址数（DexScreener 没有这个）。每次最多 30 个池子。"""
    out = {}
    pools = [p for p in pool_addrs if p]
    for i in range(0, len(pools), 30):
        batch = pools[i:i + 30]
        res = get_json("geckoterminal",
                       f"https://api.geckoterminal.com/api/v2/networks/{CHAIN_GT}/pools/multi/{','.join(batch)}")
        for d in (res or {}).get("data", []) or []:
            a = d.get("attributes", {})
            tx = a.get("transactions") or {}
            h1, h24 = tx.get("h1") or {}, tx.get("h24") or {}
            out[(a.get("address") or "").lower()] = dict(
                buyers_h1=h1.get("buyers"), sellers_h1=h1.get("sellers"),
                buyers_h24=h24.get("buyers"), sellers_h24=h24.get("sellers"),
            )
    return out


# ---------------- Blockscout：持币数 / Top10 ----------------

def _bs(path):
    sep = "&" if "?" in path else "?"
    key = f"{sep}apikey={BLOCKSCOUT_KEY}" if BLOCKSCOUT_KEY else ""
    return get_json("blockscout", f"{BLOCKSCOUT}{path}{key}")


def bs_token(addr):
    r = _bs(f"/tokens/{addr}")
    if not r:
        return None
    holders = r.get("holders_count", r.get("holders"))
    try:
        holders = int(holders) if holders is not None else None
    except (TypeError, ValueError):
        holders = None
    return {"holders": holders, "total_supply": _f(r.get("total_supply"))}


def bs_top10_pct(addr, total_supply, exclude=()):
    """Top10 持仓占比（%）。exclude 传入池子地址，把 LP 池剔除掉，不然 Top1 永远是池子。"""
    if not total_supply:
        return None
    r = _bs(f"/tokens/{addr}/holders")
    items = (r or {}).get("items") or []
    ex = {e.lower() for e in exclude if e}
    vals = []
    for it in items:
        h = ((it.get("address") or {}).get("hash") or "").lower()
        if h in ex or (it.get("address") or {}).get("is_contract"):
            continue    # 合约地址（池子/金库/销毁合约）不算在 Top10 里
        vals.append(_f(it.get("value")) or 0)
        if len(vals) == 10:
            break
    return round(100 * sum(vals) / total_supply, 2) if vals else None


# ---------------- 交易所状态 ----------------

def binance_alpha():
    r = get_json("binance", "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list")
    rows = []
    for t in (r or {}).get("data") or []:
        rows.append(dict(symbol=(t.get("symbol") or "").upper(), chain_id=str(t.get("chainId") or ""),
                         address=(t.get("contractAddress") or "").lower(),
                         since_ms=t.get("listingTime"), offline=bool(t.get("offline") or t.get("offsell"))))
    return rows


def _perp_bases(info):
    """Binance/Aster 同构 exchangeInfo → {BASE: onboardDate_ms}。1000PEPE 这类前缀去掉。"""
    out = {}
    for s in (info or {}).get("symbols") or []:
        if s.get("contractType") not in (None, "PERPETUAL") or s.get("quoteAsset") not in ("USDT", "USDC", "USD1"):
            continue
        base = (s.get("baseAsset") or "").upper()
        for pre in ("1000000", "10000", "1000", "1M"):
            if base.startswith(pre) and len(base) > len(pre):
                base = base[len(pre):]
                break
        od = s.get("onboardDate")
        if base and (base not in out or (od and od < (out[base] or 1e18))):
            out[base] = od
    return out


def binance_perp():
    return _perp_bases(get_json("binance", "https://fapi.binance.com/fapi/v1/exchangeInfo"))


def aster_perp():
    return _perp_bases(get_json("aster", "https://fapi.asterdex.com/fapi/v1/exchangeInfo"))


def binance_spot():
    r = get_json("binance", "https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT")
    return {(s.get("baseAsset") or "").upper() for s in (r or {}).get("symbols") or []
            if s.get("status") == "TRADING"}


def binance_spot_first_ms(base):
    """现货没有上线日期字段 → 用第一根日 K 的开盘时间当上线日（只对少数命中的币调用）。"""
    r = get_json("binance", f"https://api.binance.com/api/v3/klines?symbol={base}USDT&interval=1d&startTime=0&limit=1")
    return r[0][0] if isinstance(r, list) and r else None


def hl_perp():
    r = get_json("hyperliquid", "https://api.hyperliquid.xyz/info", body={"type": "meta"})
    out = set()
    for u in (r or {}).get("universe") or []:
        if u.get("isDelisted"):
            continue
        raw = u.get("name") or ""
        out.add((raw[1:] if raw.startswith("k") and raw[1:2].isupper() else raw).upper())  # kPEPE → PEPE
    return out


def gt_ohlcv_hourly(pool, limit=168):
    """过去 7 天小时 K。返回 [(ts, o, h, l, c, v_usd)]。"""
    r = get_json("geckoterminal",
                 f"https://api.geckoterminal.com/api/v2/networks/{CHAIN_GT}/pools/{pool}/ohlcv/hour"
                 f"?aggregate=1&limit={limit}&currency=usd")
    lst = (((r or {}).get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
    return [tuple(x[:6]) for x in lst if len(x) >= 6]
