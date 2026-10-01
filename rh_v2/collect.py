"""每小时跑一次。顺序：宇宙 → 全量快照 → 观察池深挖 → 交易所状态(每日) → 评分/状态机 → 看板/告警。
任何一步失败都不影响已经落库的数据；缺的字段在评分里自动跳过（权重重新归一）。"""
import os
import time
import traceback

import config as C
import db
import sources as S
import scoring
import listing_table as LT
import dashboard


def hour_ts(t=None):
    t = int(t or time.time())
    return t - t % 3600


def refresh_universe(con, now, force=False):
    last = int(db.meta_get(con, "universe_ts", 0))
    if not force and now - last < C.UNIVERSE_REFRESH_HOURS * 3600:
        return 0
    rows = S.gt_universe(C.GT_UNIVERSE_PAGES)
    if os.path.exists(C.EXTRA_TOKENS_FILE):      # 你现有网站的 460 个币地址，一行一个，直接并进来
        for line in open(C.EXTRA_TOKENS_FILE, encoding="utf-8"):
            a = line.strip().split(",")[0].lower()
            if a.startswith("0x") and len(a) == 42:
                rows.append({"address": a, "symbol": None, "name": None, "top_pool": None, "dex": None, "source": "extra"})
    new = 0
    for r in rows:
        cur = con.execute("INSERT OR IGNORE INTO tokens(address,symbol,name,first_seen,top_pool,dex,source) "
                          "VALUES(?,?,?,?,?,?,?)",
                          (r["address"], r["symbol"], r["name"], now, r["top_pool"], r["dex"], r["source"]))
        new += cur.rowcount
    if rows:
        db.meta_set(con, "universe_ts", now)
    con.commit()
    return new


def active_tokens(con, now):
    """大部分死币不必每小时拉：最新池深 < $5k 的，只在每天 00:00 UTC 那一轮复查。"""
    if now % 86400 == 0:
        return [r[0] for r in con.execute("SELECT address FROM tokens")]
    return [r[0] for r in con.execute("""
        SELECT t.address FROM tokens t
        LEFT JOIN (SELECT address, liq FROM snapshots s1
                   WHERE ts=(SELECT MAX(ts) FROM snapshots s2 WHERE s2.address=s1.address)) l USING(address)
        WHERE l.liq IS NULL OR l.liq >= 5000""")]


def snapshot(con, now):
    addrs = active_tokens(con, now)
    data = S.ds_tokens(addrs)
    obs = []
    for a, d in data.items():
        in_obs = int((d["liq"] or 0) >= C.OBS_MIN_LIQ and (d["vol_h24"] or 0) >= C.OBS_MIN_VOL24)
        con.execute("""INSERT OR REPLACE INTO snapshots
            (ts,address,price,mcap,fdv,liq,vol_h1,vol_h6,vol_h24,buys_h1,sells_h1,buys_h6,sells_h6,
             buys_h24,sells_h24,pc_h1,pc_h6,pc_h24,n_pairs,in_obs)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (now, a, d["price"], d["mcap"], d["fdv"], d["liq"], d["vol_h1"], d["vol_h6"], d["vol_h24"],
             d["buys_h1"], d["sells_h1"], d["buys_h6"], d["sells_h6"], d["buys_h24"], d["sells_h24"],
             d["pc_h1"], d["pc_h6"], d["pc_h24"], d["n_pairs"], in_obs))
        con.execute("""UPDATE tokens SET symbol=COALESCE(?,symbol), name=COALESCE(?,name), top_pool=?, dex=?,
                       pair_created=MIN(COALESCE(pair_created, ?), ?) WHERE address=?""",
                    (d["symbol"], d["name"], d["top_pool"], d["dex"], d["pair_created"], d["pair_created"], a))
        if in_obs:
            obs.append((a, d["top_pool"]))
    con.commit()
    return len(addrs), len(data), obs


def deep_dive(con, now, obs, deadline=None):
    """只对观察池：Blockscout 持币数（每小时）、Top10（每 6 小时）、GT 独立买家数（每小时）。
    deadline：绝对时间戳，到点后剩余币跳过。返回跳过的币数。"""
    flows = S.gt_pool_flows([p for _, p in obs])
    do_top10 = (now // 3600) % 6 == 0
    skipped_tokens = 0
    for i, (addr, pool) in enumerate(obs, 1):
        if deadline is not None and time.time() >= deadline:
            skipped_tokens = len(obs) - i + 1
            print(f"[{time.strftime('%H:%M:%S')}]    深挖到点，剩余 {skipped_tokens} 个币本轮跳过", flush=True)
            break
        if i == 1 or i % 10 == 0:
            print(f"[{time.strftime('%H:%M:%S')}]    深挖进度 {i}/{len(obs)}", flush=True)
        upd = {}
        bt = S.bs_token(addr)
        if bt:
            upd["holders"] = bt["holders"]
            if do_top10:
                upd["top10_pct"] = S.bs_top10_pct(addr, bt["total_supply"], exclude=[pool])
        if "top10_pct" not in upd:     # 非 6 小时整点：沿用上一次的 Top10
            prev = con.execute("SELECT top10_pct FROM snapshots WHERE address=? AND top10_pct IS NOT NULL "
                               "ORDER BY ts DESC LIMIT 1", (addr,)).fetchone()
            upd["top10_pct"] = prev[0] if prev else None
        upd.update(flows.get((pool or "").lower(), {}))
        if upd:
            sets = ",".join(f"{k}=?" for k in upd)
            con.execute(f"UPDATE snapshots SET {sets} WHERE ts=? AND address=?", (*upd.values(), now, addr))
    con.commit()
    return skipped_tokens


def run_once(force_universe=False, force_listings=False):
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] 开始运行...", flush=True)
    S.reset_stats()
    con = db.connect()
    now = hour_ts()
    deadline = t0 + C.BUDGET_SECS
    log = {"ts": now, "steps": {}, "skipped": []}

    def left():
        return deadline - time.time()

    def skip(name, why=""):
        log["skipped"].append(name + (f"({why})" if why else ""))
        print(f"[{time.strftime('%H:%M:%S')}]    ⤼ 跳过 {name} {why}", flush=True)

    def step_done(name, t):
        secs = round(time.time() - t, 1)
        log["steps"][name] = secs
        print(f"[{time.strftime('%H:%M:%S')}]    ↳ {name} 用时 {secs}s", flush=True)

    def checkpoint(phase):
        chk = dict(log)
        chk["phase"] = phase
        chk["secs"] = round(time.time() - t0, 1)
        db.meta_set(con, "last_run", chk)
        con.commit()

    try:
        t = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] 1. 刷新宇宙...", flush=True)
        log["universe_new"] = refresh_universe(con, now, force_universe)
        print(f"[{time.strftime('%H:%M:%S')}]    新增 {log['universe_new']} 个代币", flush=True)
        step_done("universe", t)

        t = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] 2. 拉取快照...", flush=True)
        log["queried"], log["got"], obs = snapshot(con, now)
        log["obs"] = len(obs)
        print(f"[{time.strftime('%H:%M:%S')}]    查询 {log['queried']}, 获得 {log['got']}, 观察池 {log['obs']}", flush=True)
        step_done("snapshot", t)
        checkpoint("snapshot_done")     # 关键步骤已完成：即使后面被杀/超时也留痕

        # ---- 以下均为非关键步骤，受总预算约束 ----
        if left() > 30:
            t = time.time()
            print(f"[{time.strftime('%H:%M:%S')}] 3. 深挖观察池...", flush=True)
            log["deep_skipped_tokens"] = deep_dive(con, now, obs, deadline=deadline)
            step_done("deep_dive", t)
        else:
            log["deep_skipped_tokens"] = len(obs)
            skip("deep_dive", "预算不足")

        last_l = int(db.meta_get(con, "listings_ts", 0))
        if not (force_listings or now - last_l >= 86400):
            pass
        elif left() < 90:
            skip("listings", "预算不足，下个每日窗口再刷")
        else:
            t = time.time()
            print(f"[{time.strftime('%H:%M:%S')}] 4. 刷新交易所列表...", flush=True)
            listings_deadline = min(deadline, time.time() + C.LISTINGS_BUDGET_SECS)
            res = LT.refresh_listings(con, now, deadline=listings_deadline)
            log["listings"] = res
            step_done("listings", t)
            if res.get("ok"):
                db.meta_set(con, "listings_ts", now)

        if left() <= 0:
            skip("rates")
            skip("scoring")
            skip("dashboard")
            skip("alert", "预算耗尽")
        else:
            t = time.time()
            print(f"[{time.strftime('%H:%M:%S')}] 5. 计算频率表...", flush=True)
            rates = LT.base_rates(con, now)
            step_done("rates", t)

            t = time.time()
            print(f"[{time.strftime('%H:%M:%S')}] 6. 评分和状态机...", flush=True)
            prev_states = {r[0]: r[1] for r in con.execute("SELECT address, state FROM state")}
            scored = scoring.score_all(con, now, LT.venues(con), rates)
            con.commit()
            log["states"] = {}
            for s in scored:
                log["states"][s["state"]] = log["states"].get(s["state"], 0) + 1
            step_done("scoring", t)

            if left() <= 0:
                skip("dashboard")
                skip("alert", "预算耗尽")
            else:
                t = time.time()
                print(f"[{time.strftime('%H:%M:%S')}] 7. 生成看板...", flush=True)
                dashboard.build(con, now, rates)
                step_done("dashboard", t)

                t = time.time()
                print(f"[{time.strftime('%H:%M:%S')}] 8. 发送告警...", flush=True)
                dashboard.alert(con, now, prev_states, scored)
                step_done("alert", t)
    except Exception:
        log["error"] = traceback.format_exc()
        print(f"[{time.strftime('%H:%M:%S')}] 错误: {log['error']}", flush=True)
    log["phase"] = "done"
    log["sources"] = S.snapshot_stats()
    log["secs"] = round(time.time() - t0, 1)
    db.meta_set(con, "last_run", log)
    con.commit()
    con.close()
    print(f"[{time.strftime('%H:%M:%S')}] 完成！用时 {log['secs']} 秒", flush=True)
    return log
