"""静态看板（单文件 HTML，可直接双击打开或丢到任何静态托管）+ Telegram 告警。"""
import html
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import config as C
import listing_table as LT

ORDER = ["READY", "RESEARCH", "ACCELERATING", "WATCH", "OVERHEATED", "INVALID"]


def rows_for(con, now):
    q = """SELECT sc.*, s.price, s.liq, s.vol_h24, s.pc_h24, s.pc_h6, s.holders, s.top10_pct, s.mcap,
                  t.symbol, t.name, t.top_pool,
                  (SELECT GROUP_CONCAT(venue || CASE WHEN match_by='symbol' THEN '?' ELSE '' END, ' ')
                     FROM listings l WHERE l.address=sc.address) venues
           FROM scores sc JOIN snapshots s USING(ts, address) JOIN tokens t USING(address)
           WHERE sc.ts=?"""
    out = [dict(r) for r in con.execute(q, (now,))]
    out.sort(key=lambda r: (ORDER.index(r["state"]) if r["state"] in ORDER else 9, -(r["heat"] or 0)))
    return out


def build(con, now, rates):
    os.makedirs(C.OUT_DIR, exist_ok=True)
    rows = rows_for(con, now)
    stamp = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d %H:00 UTC")
    with open(os.path.join(C.OUT_DIR, "dashboard.json"), "w", encoding="utf-8") as f:
        json.dump({"ts": now, "rows": rows}, f, ensure_ascii=False, default=str)
    with open(os.path.join(C.OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__DATA__", json.dumps(rows, ensure_ascii=False, default=str).replace("</", "<\\/"))
                    .replace("__STAMP__", stamp)
                    .replace("__RATES__", html.escape(LT.report(rates))))


def _tg(text):
    if not (C.TG_TOKEN and C.TG_CHAT):
        return
    data = urllib.parse.urlencode({"chat_id": C.TG_CHAT, "text": text, "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{C.TG_TOKEN}/sendMessage", data=data, timeout=10)
    except Exception:
        pass


def alert(con, now, prev_states, scored):
    """只在「新进入」READY / RESEARCH 时发，避免每小时刷屏。"""
    msgs = []
    for s in scored:
        if s["state"] in ("READY", "RESEARCH") and prev_states.get(s["address"]) != s["state"]:
            sym = con.execute("SELECT symbol FROM tokens WHERE address=?", (s["address"],)).fetchone()[0]
            msgs.append(f"{s['state']} {sym}  H{s['heat']:.0f} Q{s['quality']:.0f} E{s['entry']:.0f} "
                        f"L:{s['listing_p']}\nhttps://dexscreener.com/{C.CHAIN_DS}/{s['address']}")
    if msgs:
        _tg("RH V2\n\n" + "\n\n".join(msgs[:10]))


PAGE = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>RH V2 看板</title>
<style>
:root{--bg:#fafaf8;--fg:#1b1b1a;--mut:#6b6a66;--line:#e4e2dc;--card:#fff;
--ready:#0b7a3b;--research:#1d5fbf;--accel:#9a6a00;--watch:#6b6a66;--hot:#b3261e;--inv:#a8a6a0}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe6;--mut:#9b9a94;--line:#2c2b28;--card:#1c1b19;
--ready:#4cc27f;--research:#6fa3ff;--accel:#e0b44a;--watch:#9b9a94;--hot:#ff7a6e;--inv:#5c5b57}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,system-ui,"PingFang SC",sans-serif}
header{padding:16px;border-bottom:1px solid var(--line)}h1{font-size:18px;margin:0 0 4px}.mut{color:var(--mut)}
.bar{display:flex;gap:6px;flex-wrap:wrap;padding:10px 16px}.bar button{border:1px solid var(--line);background:var(--card);
color:var(--fg);border-radius:999px;padding:4px 10px;cursor:pointer}.bar button.on{border-color:var(--fg)}
.wrap{overflow-x:auto;padding:0 16px 16px}table{border-collapse:collapse;width:100%;min-width:980px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th{position:sticky;top:0;background:var(--bg);cursor:pointer;font-weight:600}td.l,th.l{text-align:left}
.st{font-weight:700;font-size:12px}.READY{color:var(--ready)}.RESEARCH{color:var(--research)}.ACCELERATING{color:var(--accel)}
.WATCH{color:var(--watch)}.OVERHEATED{color:var(--hot)}.INVALID{color:var(--inv)}
.why{max-width:360px;white-space:normal;text-align:left;color:var(--mut);font-size:12px}
a{color:inherit}pre{padding:0 16px 24px;color:var(--mut);font-size:12px;overflow-x:auto}
</style></head><body>
<header><h1>RH V2 · Heat / Quality / ListingP / Entry</h1>
<div class="mut">快照 __STAMP__ · 只含观察池（池深≥$25k 且 24h 量≥$20k）· 没有综合分，四列各看各的</div></header>
<div class="bar" id="bar"></div>
<div class="wrap"><table><thead><tr id="hd"></tr></thead><tbody id="tb"></tbody></table></div>
<pre>ListingP 频率表（n&lt;20 的格子显示「不定」，不输出数字）
__RATES__</pre>
<script>
const D=__DATA__;const E=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));const S=["READY","RESEARCH","ACCELERATING","WATCH","OVERHEATED","INVALID"];
const f0=v=>v==null?"–":(+v).toFixed(0),f1=v=>v==null?"–":(+v).toFixed(1),
usd=v=>v==null?"–":v>=1e6?"$"+(v/1e6).toFixed(2)+"M":"$"+(v/1e3).toFixed(0)+"k",pct=v=>v==null?"–":(v>0?"+":"")+(+v).toFixed(0)+"%";
const C=[["state","状态",r=>`<span class="st ${r.state}">${r.state}</span>`,1],
["symbol","币",r=>`<a target=_blank href="https://dexscreener.com/robinhood/${r.address}">${E(r.symbol||r.address.slice(0,8))}</a>`,1],
["heat","Heat",r=>f0(r.heat)],["quality","Quality",r=>f0(r.quality)],["listing_p","ListingP",r=>E(r.listing_p)],["entry","Entry",r=>f0(r.entry)],
["liq","池深",r=>usd(r.liq)],["vol_h24","24h量",r=>usd(r.vol_h24)],["pc_h24","24h",r=>pct(r.pc_h24)],
["vol_accel_6v18","量比6/18",r=>f1(r.vol_accel_6v18)+"x"],["vol_liq","Vol/LP",r=>f1(r.vol_liq)],
["holder_g6","持币6h",r=>r.holder_g6==null?"–":f1(r.holder_g6)+"%"],["runup_from_low","距低点",r=>f1(r.runup_from_low)+"x"],
["venues","上所",r=>E(r.venues||""),1],["reasons","依据",r=>{let w="";try{w=JSON.parse(r.reasons).join(" · ")}catch(e){}return E(w+" | "+(r.listing_basis||""))},1]];
let flt=null,sk=null,sd=-1;
function bar(){const b=document.getElementById("bar");b.innerHTML="";[null,...S].forEach(s=>{const n=s?D.filter(r=>r.state===s).length:D.length;
const x=document.createElement("button");x.textContent=(s||"全部")+" "+n;x.className=flt===s?"on":"";x.onclick=()=>{flt=s;draw()};b.appendChild(x)})}
function draw(){bar();document.getElementById("hd").innerHTML=C.map((c,i)=>`<th class="${c[3]?"l":""}" data-i=${i}>${c[1]}</th>`).join("");
document.querySelectorAll("th").forEach(th=>th.onclick=()=>{const k=C[th.dataset.i][0];sd=sk===k?-sd:-1;sk=k;draw()});
let R=D.filter(r=>!flt||r.state===flt);if(sk)R=[...R].sort((a,b)=>{const x=a[sk],y=b[sk];return (x==null)-(y==null)||(x>y?1:x<y?-1:0)*-sd});
document.getElementById("tb").innerHTML=R.map(r=>"<tr>"+C.map(c=>`<td class="${c[3]?"l":""}${c[0]==="reasons"?" why":""}">${c[2](r)}</td>`).join("")+"</tr>").join("")}
draw();
</script></body></html>"""
