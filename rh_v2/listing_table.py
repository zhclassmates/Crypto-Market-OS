"""交易所状态 + ListingP 频率表。
关键点：币安 Alpha 列表自带 listingTime，币安永续 exchangeInfo 自带 onboardDate。
所以「Alpha → 永续」的历史升档表不用手工对公告，一次 API 就能拉全（全链、所有 Alpha 币）。
现货没有上线字段，用第一根日 K 当上线日。
"""
import time

import config as C
import sources as S

DAY_MS = 86_400_000
WINDOWS = {"7": 7, "30": 30, "90": 90}


def refresh_listings(con, now=None, deadline=None):
    """deadline：绝对时间戳。现货首根日 K 是逐币调用，到点后剩余的本轮跳过，
    已写入的 perp/alpha 不回滚，下一轮每日窗口继续补 spot_ms。"""
    now = now or int(time.time())
    alpha = S.binance_alpha()
    if not alpha:
        return {"ok": False, "why": "币安 Alpha 列表拉取失败"}
    perp, spot = S.binance_perp(), S.binance_spot()
    aster, hl = S.aster_perp(), S.hl_perp()
    spot_skipped = 0

    # ---- 1) 全链 Alpha 升档事件表 ----
    for t in alpha:
        if not t["symbol"] or not t["since_ms"]:
            continue
        a_ms = int(t["since_ms"])
        p_ms = perp.get(t["symbol"])
        if p_ms and p_ms < a_ms - DAY_MS:
            p_ms = -1          # 永续早于 Alpha：要么撞名、要么本来就上过 → 不进分母
        old = con.execute("SELECT spot_ms FROM binance_events WHERE symbol=? AND chain_id=? AND address=?",
                          (t["symbol"], t["chain_id"], t["address"])).fetchone()
        s_ms = old["spot_ms"] if old else None
        if s_ms is None and t["symbol"] in spot:
            if deadline is not None and time.time() >= deadline:
                spot_skipped += 1
                continue
            s_ms = S.binance_spot_first_ms(t["symbol"])
            if s_ms and s_ms < a_ms - DAY_MS:
                s_ms = -1
        con.execute("INSERT OR REPLACE INTO binance_events VALUES(?,?,?,?,?,?)",
                    (t["symbol"], t["chain_id"], t["address"], a_ms, p_ms, s_ms))

    # ---- 2) 本链宇宙的交易所状态 ----
    alpha_by_addr = {t["address"]: t for t in alpha if t["chain_id"] == C.CHAIN_ID}
    toks = con.execute("""SELECT t.address, t.symbol,
                          (SELECT mcap FROM snapshots s WHERE s.address=t.address ORDER BY ts DESC LIMIT 1) mcap
                          FROM tokens t""").fetchall()
    n = 0
    for tk in toks:
        addr, sym = tk["address"], (tk["symbol"] or "").upper()
        rows = []
        a = alpha_by_addr.get(addr)
        if a:
            rows.append((addr, sym, "binance_alpha", a["since_ms"], "address"))
            ev = con.execute("SELECT perp_ms, spot_ms FROM binance_events WHERE chain_id=? AND address=?",
                             (C.CHAIN_ID, addr)).fetchone()
            if ev and ev["perp_ms"] and ev["perp_ms"] > 0:
                rows.append((addr, sym, "binance_perp", ev["perp_ms"], "alpha_symbol"))
            if ev and ev["spot_ms"] and ev["spot_ms"] > 0:
                rows.append((addr, sym, "binance_spot", ev["spot_ms"], "alpha_symbol"))
        # Aster / HL 只能按符号匹配 → 市值 < $1M 的不认（撞名概率太高）
        if sym and (tk["mcap"] or 0) >= 1_000_000:
            if sym in aster:
                rows.append((addr, sym, "aster_perp", aster[sym], "symbol"))
            if sym in hl:
                prev = con.execute("SELECT since_ms FROM listings WHERE address=? AND venue='hl_perp'",
                                   (addr,)).fetchone()
                rows.append((addr, sym, "hl_perp", prev["since_ms"] if prev else now * 1000, "symbol"))
        for r in rows:
            con.execute("INSERT OR REPLACE INTO listings VALUES(?,?,?,?,?,?)", (*r, now))
            n += 1
    con.commit()
    return {"ok": True, "alpha_total": len(alpha), "rh_alpha": len(alpha_by_addr),
            "universe_hits": n, "spot_skipped": spot_skipped}


def venues(con):
    out = {}
    for r in con.execute("SELECT address, venue, match_by FROM listings"):
        out.setdefault(r["address"], set()).add(r["venue"] + ("?" if r["match_by"] == "symbol" else ""))
    return out


def base_rates(con, now=None):
    """返回 {(chain, era): {n7,p7,n30,p30,n90,p90}}。
    删失处理：只有「Alpha 上线日 + 窗口 ≤ 今天」的币才进分母，否则还看不到结果，不能算 0。"""
    now_ms = (now or int(time.time())) * 1000
    evs = con.execute("SELECT chain_id, alpha_ms, perp_ms FROM binance_events WHERE alpha_ms IS NOT NULL").fetchall()
    cells = {}
    for e in evs:
        if e["perp_ms"] == -1:
            continue
        eras = ["all"]
        if e["alpha_ms"] >= C.REGIME_CUTOFF_MS:
            eras.append("post")
        if e["alpha_ms"] >= now_ms - 180 * DAY_MS:
            eras.append("recent")
        chains = ["*"] + ([C.CHAIN_ID] if e["chain_id"] == C.CHAIN_ID else [])
        for ch in chains:
            for era in eras:
                c = cells.setdefault((ch, era), {f"{k}{w}": 0 for w in WINDOWS for k in ("n", "h")})
                for w, d in WINDOWS.items():
                    if e["alpha_ms"] + d * DAY_MS > now_ms:
                        continue
                    c["n" + w] += 1
                    if e["perp_ms"] and e["perp_ms"] - e["alpha_ms"] <= d * DAY_MS:
                        c["h" + w] += 1
    out = {}
    for k, c in cells.items():
        out[k] = {}
        for w in WINDOWS:
            out[k]["n" + w] = c["n" + w]
            out[k]["p" + w] = 100 * c["h" + w] / c["n" + w] if c["n" + w] else 0.0

    # 自有样本：RH 观察池币（首次入池时还不是 Alpha）30 天内上 Alpha 的比例
    first = con.execute("SELECT address, MIN(ts) t0 FROM snapshots WHERE in_obs=1 GROUP BY address").fetchall()
    al = {r["address"]: r["since_ms"] for r in con.execute(
        "SELECT address, since_ms FROM listings WHERE venue='binance_alpha'")}
    n = h = 0
    for r in first:
        t0 = r["t0"] * 1000
        if t0 + 30 * DAY_MS > now_ms or (al.get(r["address"]) and al[r["address"]] <= t0):
            continue
        n += 1
        h += 1 if al.get(r["address"]) and al[r["address"]] <= t0 + 30 * DAY_MS else 0
    out[("own_rh_alpha30", "post")] = {"n30": n, "p30": 100 * h / n if n else 0.0}
    return out


def report(rates):
    lines = ["格子                     n7   p7%   n30  p30%   n90  p90%"]
    names = {"*": "全链", C.CHAIN_ID: "RH链"}
    for (ch, era), r in sorted(rates.items(), key=lambda x: (x[0][0] != "*", x[0][1])):
        if ch == "own_rh_alpha30":
            lines.append(f"RH观察池→Alpha(自有)       -     -  {r['n30']:4d} {r['p30']:5.1f}     -     -")
            continue
        flag = lambda n, p: f"{n:4d} {p:5.1f}" if n >= C.LISTING_MIN_N else f"{n:4d}  不定"
        lines.append(f"Alpha→永续 {names.get(ch, ch):4s} {era:6s} "
                     f"{flag(r['n7'], r['p7'])}  {flag(r['n30'], r['p30'])}  {flag(r['n90'], r['p90'])}")
    return "\n".join(lines)
