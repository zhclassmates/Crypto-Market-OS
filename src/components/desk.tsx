import { useEffect, useState } from "react";
import {
  ArrowUpRight,
  Bell,
  ChartNoAxesCombined,
  Compass,
  Eye,
  Layers3,
  ListFilter,
  Radar,
  ShieldCheck,
  Sparkles,
  Star,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { WmReasoningView } from "@/components/wm-reasoning-view";
import { AccessView } from "@/components/access-view";
import { AlertsView, DiscoveryView } from "@/components/discovery-view";
import { LadderView } from "@/components/ladder-view";
import { EarlyView } from "@/components/early-view";
import { MarketView } from "@/components/market-view";
import { MethodView } from "@/components/method-view";
import { RadarView } from "@/components/radar-view";
import { ScoreView } from "@/components/score-view";
import { StreakView } from "@/components/streak-view";

type Tab =
  | "reasoning"
  | "ladder"
  | "market"
  | "early"
  | "discovery"
  | "access"
  | "alerts"
  | "score"
  | "streak"
  | "radar"
  | "method"
  | "watch";

const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: "reasoning", label: "推演", hint: "证据与自我纠错" },
  { id: "ladder", label: "上币阶梯", hint: "走到了哪一级" },
  { id: "market", label: "市场排行", hint: "N日涨跌幅" },
  { id: "early", label: "早期观察", hint: "EARLY $20k–$50k" },
  { id: "discovery", label: "爆款发现", hint: "活跃度加速" },
  { id: "access", label: "新入口", hint: "上币与买入通道" },
  { id: "alerts", label: "告警", hint: "条件命中" },
  { id: "score", label: "四列", hint: "当场拉数打分" },
  { id: "streak", label: "日K连涨", hint: "离线算 pattern" },
  { id: "radar", label: "强平雷达", hint: "拥挤与去杠杆" },
  { id: "method", label: "口径", hint: "规则写在明处" },
  { id: "watch", label: "自选", hint: "盯住的代币" },
];

const HASH: Record<Tab, string> = {
  reasoning: "#sec-reasoning",
  ladder: "#sec-ladder",
  market: "#sec-market",
  early: "#sec-early",
  discovery: "#sec-discovery",
  access: "#sec-access",
  alerts: "#sec-alerts",
  score: "#sec-score",
  streak: "#sec-streak",
  radar: "#sec-radar",
  method: "#sec-method",
  watch: "#sec-watch",
};

const PRESENTATION: Record<Tab, { title: string; description: string; icon: LucideIcon }> = {
  reasoning: { title: "让判断接受证据检验。", description: "识别变化，提出可被推翻的假设，记录新增支持与反证。每一步先验证，再行动。", icon: Compass },
  ladder: {
    title: "看清每一步上币进阶。",
    description:
      "从链上发行到交易所上市，追踪每一级门槛。Robinhood App 与交易所，两条路径分开核实。",
    icon: Layers3,
  },
  market: {
    title: "把握多链市场的变化。",
    description: "汇集多链代币行情、日度涨跌与成交量，在同一张表里发现值得关注的变化。",
    icon: ChartNoAxesCombined,
  },
  early: {
    title: "更早看见链上机会。",
    description: "关注 EARLY 阶段的代币，在市值与流动性之间，找到下一步值得研究的线索。",
    icon: Eye,
  },
  discovery: {
    title: "发现正在加速的热度。",
    description: "从活跃度和成交变化中识别加速信号，把市场噪声转化为清晰的观察清单。",
    icon: Sparkles,
  },
  access: {
    title: "追踪每一个新入口。",
    description: "汇集上币事件与买入通道，核对来源、时间与状态，让市场的新变化有据可查。",
    icon: Compass,
  },
  alerts: {
    title: "让重要变化主动出现。",
    description: "设置你的观察条件，汇总命中信号。规则保存在当前浏览器，随时调整与查看。",
    icon: Bell,
  },
  score: {
    title: "用四个维度读懂代币。",
    description: "热度、质量、上币概率与入场状态，一次核对，把判断依据放在明处。",
    icon: ListFilter,
  },
  streak: {
    title: "读懂日 K 的持续性。",
    description: "观察连续上涨与价格形态，在日度数据中寻找趋势的延续和变化。",
    icon: TrendingUp,
  },
  radar: {
    title: "看见拥挤与去杠杆。",
    description: "观察市场拥挤度、持仓变化与强平信号，为行情变化补上另一种视角。",
    icon: Radar,
  },
  method: {
    title: "每一个判断，都有依据。",
    description: "公开数据来源、计算口径与筛选规则，让每一项指标都可以理解和核对。",
    icon: ShieldCheck,
  },
  watch: {
    title: "专注你关心的代币。",
    description: "把关注的代币放在一起，持续查看行情与上币进展。自选清单保存在当前浏览器。",
    icon: Star,
  },
};

function tabFromHash(hash: string): Tab | null {
  const h = hash.replace("#", "");
  if (h === "reasoning" || h === "sec-reasoning") return "reasoning";
  if (h === "score" || h === "sec-score") return "score";
  if (h === "market" || h === "sec-market") return "market";
  if (h === "early" || h === "sec-early") return "early";
  if (h === "discovery" || h === "sec-discovery") return "discovery";
  if (h === "access" || h === "sec-access") return "access";
  if (h === "alerts" || h === "sec-alerts") return "alerts";
  if (h === "streak" || h === "sec-streak") return "streak";
  if (h === "radar" || h === "sec-radar") return "radar";
  if (h === "method" || h === "sec-method") return "method";
  if (h === "ladder" || h === "sec-ladder") return "ladder";
  if (h === "watch" || h === "sec-watch") return "watch";
  return null;
}

export function Desk() {
  const [tab, setTab] = useState<Tab>("market");

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
    <div className="app-shell min-h-screen bg-bg text-fg">
      <header className="desk-header">
        <div className="desk-masthead">
          <button
            type="button"
            onClick={() => go("ladder")}
            className="desk-brand"
            aria-label="阶梯首页"
          >
            <span className="brand-mark">
              <Layers3 size={22} strokeWidth={2.2} />
            </span>
            <span>
              阶梯<span className="brand-caption">CHAIN INTELLIGENCE</span>
            </span>
          </button>
          <div className="masthead-actions">
            <span className="masthead-label">多链观察 · 数据有据</span>
            <button type="button" className="primary-action" onClick={() => go("watch")}>
              我的自选 <ArrowUpRight size={15} />
            </button>
          </div>
        </div>
        <div className="desk-hero">
          <div className="hero-copy">
            <p className="hero-eyebrow">链上研究 / {TABS.find((t) => t.id === tab)?.label}</p>
            <h1>{PRESENTATION[tab].title}</h1>
            <p className="hero-description">{PRESENTATION[tab].description}</p>
          </div>
          <div className="hero-spectrum" aria-hidden="true" />
        </div>
        <div className="desk-navigation">
          <nav className="view-navigation" aria-label="视图">
            {TABS.map((t) => {
              const Icon = PRESENTATION[t.id].icon;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => go(t.id)}
                  aria-current={tab === t.id ? "page" : undefined}
                  title={t.hint}
                  className={"view-nav-item " + (tab === t.id ? "is-active" : "")}
                >
                  <Icon size={16} strokeWidth={1.8} />
                  <span>{t.label}</span>
                </button>
              );
            })}
          </nav>
        </div>
      </header>
      <main className="app-content" aria-label={TABS.find((t) => t.id === tab)?.label}>
        {tab === "reasoning" ? <WmReasoningView /> : null}
        {tab === "ladder" ? <LadderView /> : null}
        {tab === "market" ? <MarketView /> : null}
        {tab === "early" ? <EarlyView /> : null}
        {tab === "discovery" ? <DiscoveryView /> : null}
        {tab === "access" ? <AccessView /> : null}
        {tab === "alerts" ? <AlertsView /> : null}
        {tab === "score" ? <ScoreView /> : null}
        {tab === "streak" ? <StreakView /> : null}
        {tab === "radar" ? <RadarView /> : null}
        {tab === "method" ? <MethodView /> : null}
        {tab === "watch" ? <MarketView watchOnly /> : null}
      </main>
      <footer className="desk-footer">
        <span className="font-medium">
          阶梯 <span className="ml-2 font-normal text-muted">链上研究，清晰有据。</span>
        </span>
        <button type="button" onClick={() => go("method")} className="text-primary hover:underline">
          数据与口径 <ArrowUpRight className="ml-1 inline-block size-3.5" />
        </button>
      </footer>
    </div>
  );
}
