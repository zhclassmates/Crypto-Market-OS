"""本地假交易所：模拟 Binance / Bybit 的 REST 与 WS 返回格式，用于离线端到端测试。
另外故意制造：一次 429 限频、Binance WS 每 25 秒断线一次、一个 Bybit 不存在的品种订阅失败。
"""
import asyncio
import json
import random
import time

from aiohttp import web

IV = {"1m": 60_000, "15m": 900_000}
state = {"hit429": False}


def now():
    return int(time.time() * 1000)


def kl(req):
    q = req.query
    step = IV[q["interval"]]
    start = int(q.get("startTime", now() - 500 * step))
    start -= start % step
    limit = int(q.get("limit", 500))
    out, t = [], start
    while t <= now() and len(out) < limit:
        o = 100 + (t // step) % 7
        vq = 1000.0 + (t // step) % 13
        out.append([t, str(o), str(o + 1), str(o - 1), str(o + 0.5), "10", t + step - 1,
                    str(vq), 42, "6", str(vq * 0.6), "0"])
        t += step
    return web.json_response(out)


async def klines(req):
    if not state["hit429"]:
        state["hit429"] = True
        return web.Response(status=429, headers={"Retry-After": "1"})
    return kl(req)


async def premium(req):
    return web.json_response({"symbol": req.query["symbol"], "markPrice": "100.5", "indexPrice": "100.4",
                              "lastFundingRate": "0.00012", "nextFundingTime": now() + 3_600_000,
                              "time": now()})


async def oi(req):
    return web.json_response({"symbol": req.query["symbol"], "openInterest": "12345.6", "time": now()})


async def oi_hist(req):
    s, e = int(req.query["startTime"]), int(req.query["endTime"])
    s -= s % 300_000
    out, t = [], s
    while t <= min(e, now()) and len(out) < 500:
        out.append({"symbol": req.query["symbol"], "sumOpenInterest": "1000", "sumOpenInterestValue": "100000",
                    "timestamp": t})
        t += 300_000
    return web.json_response(out)


async def funding(req):
    s = int(req.query["startTime"])
    s = s - s % 28_800_000 + 28_800_000
    out = [{"symbol": req.query["symbol"], "fundingTime": t, "fundingRate": "0.0001", "markPrice": "100"}
           for t in range(s, now(), 28_800_000)]
    return web.json_response(out)


async def by_oi(req):
    s, e = int(req.query["startTime"]), int(req.query["endTime"])
    step = {"15min": 900_000, "5min": 300_000}[req.query["intervalTime"]]
    s -= s % step
    lst = [{"openInterest": "5000", "timestamp": str(t)} for t in range(s, min(e, now()), step)][:200]
    return web.json_response({"retCode": 0, "retMsg": "OK", "result": {"list": lst[::-1]}})


async def by_ticker(req):
    return web.json_response({"retCode": 0, "result": {"list": [{
        "symbol": req.query["symbol"], "markPrice": "100.6", "indexPrice": "100.5",
        "fundingRate": "0.0001", "openInterest": "5001", "nextFundingTime": str(now() + 1000)}]}})


async def bn_ws(req):
    ws = web.WebSocketResponse(heartbeat=10)
    await ws.prepare(req)
    t0 = time.time()
    while not ws.closed and time.time() - t0 < 25:      # 25 秒后主动断开，测重连
        side = random.choice(["SELL", "BUY"])
        await ws.send_str(json.dumps({"e": "forceOrder", "E": now(), "o": {
            "s": random.choice(["BTCUSDT", "ETHUSDT", "XYZUSDT"]), "S": side, "o": "LIMIT", "f": "IOC",
            "q": "0.5", "p": "100", "ap": "100.2", "X": "FILLED", "l": "0.5", "z": "0.5", "T": now()}}))
        await asyncio.sleep(0.5)
    await ws.close()
    return ws


async def by_ws(req):
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    topics = []

    async def pusher():
        while not ws.closed:
            for tp in topics:
                sym = tp.split(".", 1)[1]
                await ws.send_str(json.dumps({"topic": tp, "type": "snapshot", "ts": now(), "data": [
                    {"T": now(), "s": sym, "S": random.choice(["Buy", "Sell"]), "v": "0.3", "p": "100.1"}]}))
            await asyncio.sleep(0.7)

    task = asyncio.create_task(pusher())
    async for m in ws:
        d = json.loads(m.data)
        if d.get("op") == "ping":
            await ws.send_str(json.dumps({"op": "pong", "success": True}))
        elif d.get("op") == "subscribe":
            good = [a for a in d["args"] if not a.endswith("BADUSDT")]
            topics.extend(good)
            await ws.send_str(json.dumps({"op": "subscribe", "success": len(good) == len(d["args"]),
                                          "ret_msg": "" if len(good) == len(d["args"]) else "bad topic"}))
    task.cancel()
    return ws


def app():
    a = web.Application()
    a.router.add_get("/fapi/v1/klines", klines)
    a.router.add_get("/api/v3/klines", kl)
    a.router.add_get("/fapi/v1/premiumIndex", premium)
    a.router.add_get("/fapi/v1/openInterest", oi)
    a.router.add_get("/futures/data/openInterestHist", oi_hist)
    a.router.add_get("/fapi/v1/fundingRate", funding)
    a.router.add_get("/v5/market/open-interest", by_oi)
    a.router.add_get("/v5/market/tickers", by_ticker)
    a.router.add_get("/ws/!forceOrder@arr", bn_ws)
    a.router.add_get("/v5/public/linear", by_ws)
    return a


if __name__ == "__main__":
    web.run_app(app(), host="127.0.0.1", port=18080, print=None)
