"""离线自测：不连网，用假数据模拟 10 个小时，检查落库、评分、状态机、看板。
python3 test_offline.py"""
import os
import random
import tempfile

tmp = tempfile.mkdtemp()
os.environ["RHV2_DB"] = os.path.join(tmp, "t.sqlite")
os.environ["RHV2_OUT"] = os.path.join(tmp, "out")
os.environ["RHV2_EXTRA"] = os.path.join(tmp, "none.txt")

import config as C  # noqa: E402
import sources as S  # noqa: E402
import collect  # noqa: E402
import db  # noqa: E402
import listing_table as LT  # noqa: E402

random.seed(1)
T0 = 1_790_000_000 - 1_790_000_000 % 3600
A = {  # 地址: (名字, 形态)
    "0x" + "a" * 40: ("RISER", "accel"),     # 稳步加速、健康
    "0x" + "b" * 40: ("PUMP", "pump"),       # 24h +800%，Vol/LP 巨大 → OVERHEATED
    "0x" + "c" * 40: ("FLAT", "flat"),       # 平
    "0x" + "d" * 40: ("DUST", "dust"),       # 池子太浅 → 不进观察池
    "0x" + "e" * 40: ("ALPHA1", "flat"),     # 已上 Alpha
}
clock = {"h": 0}


def fake_universe(pages):
    return [dict(address=a, symbol=n, name=n, top_pool="0xpool" + a[2:8], dex="uniswap", source="gt_top")
            for a, (n, _) in A.items()]


def fake_ds(addrs):
    h = clock["h"]
    out = {}
    for a in addrs:
        n, kind = A[a]
        if kind == "accel":
            v24, v6, v1, liq, pc24, pc6, price = 400e3 + 60e3 * h, 250e3 + 40e3 * h, 70e3 + 8e3 * h, 300e3, 60, 25, 1 + 0.03 * h
        elif kind == "pump":
            v24, v6, v1, liq, pc24, pc6, price = 5e6, 3e6, 8e5, 60e3, 800, 300, 9
        elif kind == "dust":
            v24, v6, v1, liq, pc24, pc6, price = 5e3, 1e3, 100, 3e3, 5, 1, 0.1
        else:
            v24, v6, v1, liq, pc24, pc6, price = 100e3, 25e3, 4e3, 200e3, 2, 0, 1
        b6 = int(v6 / 300)
        out[a] = dict(symbol=n, name=n, top_pool="0xpool" + a[2:8], dex="uniswap", pair_created=T0 - 20 * 86400,
                      price=price, mcap=price * 1e7, fdv=price * 1e7, liq=liq, vol_h1=v1, vol_h6=v6, vol_h24=v24,
                      buys_h1=int(v1 / 250), sells_h1=int(v1 / 400), buys_h6=b6, sells_h6=int(b6 * 0.7),
                      buys_h24=int(v24 / 300), sells_h24=int(v24 / 400), pc_h1=3, pc_h6=pc6, pc_h24=pc24, n_pairs=1)
    return out


def fake_flows(pools):
    return {p.lower(): dict(buyers_h1=40 + 5 * clock["h"], sellers_h1=20, buyers_h24=400, sellers_h24=300) for p in pools}


def fake_bs(addr):
    return {"holders": 1500 + 60 * clock["h"] if A[addr][1] == "accel" else 900, "total_supply": 1e9}


S.gt_universe = fake_universe
S.ds_tokens = fake_ds
S.gt_pool_flows = fake_flows
S.bs_token = fake_bs
S.bs_top10_pct = lambda a, t, exclude=(): 22.0
DAY = 86_400_000
alpha_rows = [dict(symbol="ALPHA1", chain_id="4663", address="0x" + "e" * 40, since_ms=(T0 - 3 * 86400) * 1000, offline=False)]
for i in range(60):   # 60 个老 Alpha 币，其中 21 个 30 天内上了永续
    alpha_rows.append(dict(symbol=f"OLD{i}", chain_id="56", address=f"0x{i:040x}", since_ms=(T0 - 200 * 86400) * 1000, offline=False))
S.binance_alpha = lambda: alpha_rows
S.binance_perp = lambda: {f"OLD{i}": (T0 - 200 * 86400) * 1000 + (10 if i < 21 else 60) * DAY for i in range(60)}
S.binance_spot = lambda: set()
S.aster_perp = lambda: {"RISER": T0 * 1000}
S.hl_perp = lambda: set()

for h in range(10):
    clock["h"] = h
    collect.hour_ts = lambda t=None, h=h: T0 + h * 3600
    log = collect.run_once()
    assert "error" not in log, log["error"]
    print(h, log["obs"], log["states"])

con = db.connect()
st = {r["address"]: r["state"] for r in con.execute("SELECT * FROM state")}
print(st)
assert st["0x" + "b" * 40] == "OVERHEATED"
assert st["0x" + "a" * 40] in ("READY", "RESEARCH"), st
assert "0x" + "d" * 40 not in st                       # 浅池不进观察池
last = con.execute("SELECT listing_p, listing_basis FROM scores WHERE address=? ORDER BY ts DESC LIMIT 1",
                   ("0x" + "e" * 40,)).fetchone()
print("ALPHA1 ListingP:", tuple(last))
assert last[0] == "35%", tuple(last)                   # 21/60 = 35%，全链格子
print(LT.report(LT.base_rates(con, T0 + 9 * 3600)))
r = con.execute("SELECT * FROM scores WHERE address=? ORDER BY ts DESC LIMIT 1", ("0x" + "a" * 40,)).fetchone()
print({k: r[k] for k in r.keys()})
print("html:", os.path.getsize(os.path.join(C.OUT_DIR, "index.html")), "bytes ->", C.OUT_DIR)
print("OK")
