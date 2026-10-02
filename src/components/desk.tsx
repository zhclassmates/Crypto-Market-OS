import { useEffect, useState } from "react";
import { LadderView } from "@/components/ladder-view";
import { MarketView } from "@/components/market-view";
import { MethodView } from "@/components/method-view";
import { RadarView } from "@/components/radar-view";
import { ScoreView } from "@/components/score-view";
import { StreakView } from "@/components/streak-view";

type Tab = "ladder" | "market" | "score" | "streak" | "radar" | "method" | "watch";

const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: "ladder", label: "上币阶梯", hint: "走到了哪一级" },
  { id: "market", label: "市场排行", hint: "N日涨跌幅" },
  { id: "score", label: "四列", hint: "当场拉数打分" },
  { id: "streak", label: "日K连涨", hint: "离线算 pattern" },
  { id: "radar", label: "强平雷达", hint: "拥挤与去杠杆" },
  { id: "method", label: "口径", hint: "规则写在明处" },
  { id: "watch", label: "自选", hint: "盯住的代币" },
];

const HASH: Record<Tab, string> = {
  ladder: "#sec-ladder",
  market: "#sec-market",
  score: "#sec-score",
  streak: "#sec-streak",
  radar: "#sec-radar",
  method: "#sec-method",
  watch: "#sec-watch",
};

function tabFromHash(hash: string): Tab | null {
  const h = hash.replace("#", "");
  if (h === "score" || h === "sec-score") return "score";
  if (h === "market" || h === "sec-market") return "market";
  if (h === "streak" || h === "sec-streak") return "streak";
  if (h === "radar" || h === "sec-radar") return "radar";
  if (h === "method" || h === "sec-method") return "method";
  if (h === "ladder" || h === "sec-ladder") return "ladder";
  if (h === "watch" || h === "sec-watch") return "watch";
  return null;
}

export function Desk() {
  const [tab, setTab] = useState<Tab>("ladder");

  useEffect(() => {
    const next = tabFromHash(window.location.hash);
    if (next) setTab(next);
    const onHash = () => {
      const t = tabFromHash(window.location.hash);
      if (t) setTab(t);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  function go(id: Tab) {
    setTab(id);
    window.history.replaceState(null, "", HASH[id]);
  }

  return (
    <div className="min-h-screen bg-bg text-fg">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="font-mono text-xs tracking-widest text-brass">ROBINHOOD CHAIN</p>
            <h1 className="mt-1 text-3xl font-medium tracking-tight text-balance">阶梯</h1>
            <p className="mt-1 max-w-xl text-sm text-pretty text-muted">
              链上谁都能发。能在 Robinhood App 里买到的，和能走到币安的，是两条分开数的路。
            </p>
          </div>
          <nav className="flex flex-wrap gap-2" aria-label="视图">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => go(t.id)}
                className={
                  "min-h-11 rounded-full border px-4 text-left " +
                  (tab === t.id ? "border-brass text-fg" : "border-line text-muted")
                }
              >
                <span className="block text-sm">{t.label}</span>
                <span className="block text-xs text-muted">{t.hint}</span>
              </button>
            ))}
          </nav>
        </div>
      </header>
      {tab === "ladder" ? <LadderView /> : null}
      {tab === "market" ? <MarketView /> : null}
      {tab === "score" ? <ScoreView /> : null}
      {tab === "streak" ? <StreakView /> : null}
      {tab === "radar" ? <RadarView /> : null}
      {tab === "method" ? <MethodView /> : null}
      {tab === "watch" ? <MarketView watchOnly /> : null}
    </div>
  );
}
