"""衍生指标 + 四列评分 + 状态机。
设计原则：
- 没有综合分。Heat / Quality / ListingP / Entry 四列各说各的。
- 加速度一律用非重叠窗：近 6h 小时均量 vs 之前 18h 小时均量 = (v6/6) / ((v24-v6)/18)。
  这个可以直接从 DexScreener 的 h6/h24 窗口算，第一天就能用，不必等自有历史。
- 持币/买家增长、从低点涨了几倍、从高点回撤多少：用自有小时快照。所以要尽早开始存。
- READY 宁缺毋滥：自有快照 ≥6 小时、连续 3 小时 Heat 达标、Quality/Entry 都达标才给。
"""
import json
import math
import time

import config as C

RANK = {"INVALID": 0, "WATCH": 1, "ACCELERATING": 2, "RESEARCH": 3, "READY": 4, "OVERHEATED": 5}


def lin(x, lo, hi):
    """线性映射到 0..1，越界截断；x 为 None 返回 None。"""
    if x is None:
        return None
    if hi == lo:
        return 1.0 if x >= hi else 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def wavg(parts):
    """parts: [(权重, 0..1 或 None)]。缺数据的项不参与，权重重新归一。全缺返回 None。"""
    got = [(w, v) for w, v in parts if v is not None]
    if not got:
        return None
    return round(100 * sum(w * v for w, v in got) / sum(w for w, _ in got), 1)


def _ratio(a, b, floor):
    if a is None or b is None:
        return None
    return a / max(b, floor)


# ---------------------------------------------------------------- 特征

def features(con, s, now):
    """s: 本小时 snapshot 行（dict）。返回特征 dict。"""
    addr = s["address"]
    v1, v6, v24 = s.get("vol_h1") or 0, s.get("vol_h6") or 0, s.get("vol_h24") or 0
    t6 = (s.get("buys_h6") or 0) + (s.get("sells_h6") or 0)
    t24 = (s.get("buys_h24") or 0) + (s.get("sells_h24") or 0)
    f = {
        "vol_accel_6v18": _ratio(v6 / 6, max(v24 - v6, 0) / 18, 100.0) if v24 else None,
        "vol_accel_1v24": _ratio(v1, v24 / 24, 100.0) if v24 else None,
        "tx_accel_6v18": _ratio(t6 / 6, max(t24 - t6, 0) / 18, 1.0) if t24 else None,
        "buy_ratio_h1": _share(s.get("buys_h1"), s.get("sells_h1")),
        "buy_ratio_h6": _share(s.get("buys_h6"), s.get("sells_h6")),
        "vol_liq": (v24 / s["liq"]) if s.get("liq") else None,
        "buyer_accel": None, "holder_g6": None, "holder_g24": None,
    }
    if s.get("buyers_h1") is not None and s.get("buyers_h24"):
        f["buyer_accel"] = _ratio(s["buyers_h1"], s["buyers_h24"] / 24, 1.0)

    hist = con.execute(
        "SELECT ts, price, holders FROM snapshots WHERE address=? AND ts>=? AND ts<? ORDER BY ts",
        (addr, now - 7 * 86400, now)).fetchall()
    f["n_hist"] = con.execute("SELECT COUNT(*) FROM snapshots WHERE address=? AND ts<=?", (addr, now)).fetchone()[0]

    h_now = s.get("holders")
    if h_now:
        for key, hrs in (("holder_g6", 6), ("holder_g24", 24)):
            old = [r["holders"] for r in hist if r["holders"] and abs(r["ts"] - (now - hrs * 3600)) <= 1800]
            if old:
                f[key] = round(100 * (h_now / old[-1] - 1), 2)

    price = s.get("price")
    prices = [r["price"] for r in hist if r["price"]]
    lows = list(prices)
    highs = [r["price"] for r in hist if r["price"] and r["ts"] >= now - 72 * 3600]
    for k in con.execute("SELECT ts, h, l FROM ohlcv WHERE address=? AND ts>=? AND ts<?",
                         (addr, now - 7 * 86400, now)):
        if k["l"]:
            lows.append(k["l"])
        if k["h"] and k["ts"] >= now - 72 * 3600:
            highs.append(k["h"])
    if price and s.get("pc_h24") is not None and s["pc_h24"] > -99:
        lows.append(price / (1 + s["pc_h24"] / 100))       # 24h 前价格，历史不够时兜底
    f["runup_from_low"] = round(price / min(lows), 2) if price and lows else None
    f["dd_from_high"] = round(100 * (1 - price / max(highs + [price])), 1) if price and highs else None
    return f


def _share(b, s):
    if b is None or s is None or (b + s) == 0:
        return None
    return round(b / (b + s), 3)


# ---------------------------------------------------------------- 四列

def heat(s, f):
    return wavg([
        (35, lin(f["vol_accel_6v18"], 1.0, 3.0)),
        (20, lin(f["tx_accel_6v18"], 1.0, 3.0)),
        (15, lin(f["buyer_accel"], 1.0, 3.0)),
        (15, lin(s.get("pc_h6"), 0, 100)),
        (15, lin(f["holder_g6"], 0, 5)),
    ])


def quality(s, f, age_days):
    liq = s.get("liq") or 0
    uniq = None
    if s.get("buyers_h24") and s.get("buys_h24"):
        uniq = s["buyers_h24"] / s["buys_h24"]          # 每笔买单对应多少独立地址：越低越像刷
    return wavg([
        (25, lin(math.log10(liq) if liq > 0 else None, math.log10(25_000), 6.0)),
        (20, None if f["vol_liq"] is None else 1 - lin(f["vol_liq"], 3, 15)),   # Vol/LP 是减分项
        (20, lin(uniq, 0.15, 0.6)),
        (15, lin(math.log10(s["holders"]) if s.get("holders") else None, 2.5, 4.0)),
        (10, None if s.get("top10_pct") is None else 1 - lin(s["top10_pct"], 20, 60)),
        (10, lin(age_days, 0.5, 14)),
    ])


def entry(s, f):
    pen = 0.0
    if f["runup_from_low"] is not None:
        pen += 40 * lin(f["runup_from_low"], 2, 10)
    pen += 25 * (lin(s.get("pc_h24"), 100, 500) or 0)
    pen += 15 * (lin(f["vol_liq"], 5, 15) or 0)
    if f["buy_ratio_h1"] is not None and f["buy_ratio_h1"] < 0.45:
        pen += 10
    if f["dd_from_high"] is not None and f["dd_from_high"] > 50:
        pen += 15                                          # 从 72h 高点腰斩：趋势可能已坏
    return round(max(0.0, 100 - pen), 1)


# ---------------------------------------------------------------- ListingP

def listing_p(con, addr, venues, base_rates):
    """不做回归。已上币安永续 → 直接写；已 Alpha → 查 Alpha→永续 频率表；纯链上 → 自有样本够了才给数。
    任何格子 n < LISTING_MIN_N 一律「不确定」。"""
    tags = ",".join(sorted(venues)) or "无"
    if "binance_perp" in venues:
        return "已上币安永续", tags
    if "binance_alpha" in venues:
        for cell in (("4663", "post"), ("*", "recent"), ("*", "all")):
            r = base_rates.get(cell)
            if r and r["n30"] >= C.LISTING_MIN_N:
                label = {"4663": "RH链", "*": "全链"}[cell[0]]
                era = {"post": "9/8后", "recent": "近180天", "all": "全时段"}[cell[1]]
                return f"{r['p30']:.0f}%", f"Alpha→永续30天 {label}{era} n={r['n30']} | {tags}"
        return "不确定", f"Alpha→永续样本不足 | {tags}"
    own = base_rates.get(("own_rh_alpha30", "post"))
    if own and own["n30"] >= C.LISTING_MIN_N:
        return f"{own['p30']:.0f}%", f"RH观察池→Alpha30天 n={own['n30']} | {tags}"
    return "不确定", f"纯链上，自有样本不足 | {tags}"


# ---------------------------------------------------------------- 状态机

def target_state(s, f, h, q, e, persist):
    why = []
    liq = s.get("liq") or 0
    if liq < C.INVALID_LIQ:
        return "INVALID", [f"池深 ${liq:,.0f} < ${C.INVALID_LIQ:,}"]
    pc24 = s.get("pc_h24") or 0
    vl = f["vol_liq"] or 0
    if (pc24 > C.OVERHEAT_PC24 and vl > C.OVERHEAT_VOL_LIQ) or pc24 > C.OVERHEAT_PC24_HARD or (e is not None and e < 25):
        return "OVERHEATED", [f"24h {pc24:+.0f}%", f"Vol/LP {vl:.1f}", f"Entry {e}"]
    H, Q, E = h or 0, q or 0, e or 0
    ready_checks = {
        f"Heat≥55({H:.0f})": H >= 55,
        f"Quality≥60({Q:.0f})": Q >= 60,
        f"Entry≥60({E:.0f})": E >= 60,
        f"自有快照≥{C.READY_MIN_SNAPSHOTS}h({f['n_hist']})": f["n_hist"] >= C.READY_MIN_SNAPSHOTS,
        f"连续3h热({persist})": persist >= 3,
        "持币不降": f["holder_g6"] is None or f["holder_g6"] >= 0,
        "6h买单占优": (f["buy_ratio_h6"] or 0) >= 0.5,
    }
    if all(ready_checks.values()):
        return "READY", list(ready_checks)
    if H >= 55 and Q >= 50:
        return "RESEARCH", ["未满足: " + "、".join(k for k, ok in ready_checks.items() if not ok)]
    if (f["vol_accel_6v18"] or 0) >= 2 and (f["buy_ratio_h1"] or 0) >= 0.5:
        return "ACCELERATING", [f"6h/18h 量比 {f['vol_accel_6v18']:.1f}x"]
    return "WATCH", why


def step_state(con, addr, target, now):
    """升级立即生效；降级要连续 N 小时确认；INVALID / OVERHEATED 立即生效（安全优先）。"""
    row = con.execute("SELECT * FROM state WHERE address=?", (addr,)).fetchone()
    if not row:
        con.execute("INSERT INTO state VALUES(?,?,?,NULL,0)", (addr, target, now))
        return target
    cur = row["state"]
    if target == cur:
        con.execute("UPDATE state SET pending=NULL, pending_count=0 WHERE address=?", (addr,))
        return cur
    immediate = target in ("INVALID", "OVERHEATED") or RANK[target] > RANK[cur] or cur in ("INVALID", "OVERHEATED")
    if immediate:
        con.execute("UPDATE state SET state=?, since_ts=?, pending=NULL, pending_count=0 WHERE address=?",
                    (target, now, addr))
        return target
    cnt = (row["pending_count"] + 1) if row["pending"] == target else 1
    if cnt >= C.DOWNGRADE_CONFIRM_HOURS:
        con.execute("UPDATE state SET state=?, since_ts=?, pending=NULL, pending_count=0 WHERE address=?",
                    (target, now, addr))
        return target
    con.execute("UPDATE state SET pending=?, pending_count=? WHERE address=?", (target, cnt, addr))
    return cur


def score_all(con, now, venues_by_addr, base_rates):
    rows = con.execute("SELECT s.*, t.pair_created FROM snapshots s JOIN tokens t USING(address) "
                       "WHERE s.ts=? AND s.in_obs=1", (now,)).fetchall()
    out = []
    for r in rows:
        s = dict(r)
        f = features(con, s, now)
        age = (now - s["pair_created"]) / 86400 if s.get("pair_created") else None
        h, q, e = heat(s, f), quality(s, f, age), entry(s, f)
        prev = con.execute("SELECT heat FROM scores WHERE address=? AND ts<? ORDER BY ts DESC LIMIT 2",
                           (s["address"], now)).fetchall()
        persist = 1 if (h or 0) >= 55 else 0
        if persist:
            for p in prev:
                if (p["heat"] or 0) >= 55:
                    persist += 1
                else:
                    break
        lp, basis = listing_p(con, s["address"], venues_by_addr.get(s["address"], set()), base_rates)
        tgt, why = target_state(s, f, h, q, e, persist)
        st = step_state(con, s["address"], tgt, now)
        if st != tgt:
            why = why + [f"目标 {tgt}，降级待确认"]
        con.execute("INSERT OR REPLACE INTO scores VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            now, s["address"], f["vol_accel_6v18"], f["vol_accel_1v24"], f["tx_accel_6v18"],
            f["buy_ratio_h1"], f["buy_ratio_h6"], f["vol_liq"], f["holder_g6"], f["holder_g24"],
            f["buyer_accel"], f["runup_from_low"], f["dd_from_high"], f["n_hist"],
            h, q, e, lp, basis, st, json.dumps(why, ensure_ascii=False)))
        out.append(dict(address=s["address"], state=st, heat=h, quality=q, entry=e, listing_p=lp))
    return out
