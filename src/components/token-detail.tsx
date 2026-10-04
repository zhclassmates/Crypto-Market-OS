import { useEffect, useState, type ReactNode } from "react";
import { useServerFn } from "@tanstack/react-start";
import { X } from "lucide-react";
import { fetchTokenDetail, type TokenDetail } from "@/lib/rh/discovery-server";
import { fetchBuyEntries } from "@/lib/rh/access-server";
import { TZ_LABEL, fmtTs8, fmtTs8Full, type BuyEntry } from "@/lib/rh/access-core";
import type { SolAuthority } from "@/lib/rh/discovery";

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (v === 0) return "0";
  const a = Math.abs(v);
  if (a >= 1e9) return `${(v / 1e9).toFixed(digits)}B`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(digits)}M`;
  if (a >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  if (a >= 1) return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  return v.toPrecision(4);
}

export function fmtUsdN(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `$${fmtNum(v)}`;
}

/** 百分数输入（25 = +25%）。 */
export function fmtPctPoints(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${sign}${Math.abs(v).toFixed(1)}%`;
}

export function pctTone(v: number | null | undefined): string {
  if (v == null || v === 0) return "text-muted";
  return v > 0 ? "text-moss" : "text-clay";
}

export function fmtX(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "—" : `${v.toFixed(2)}×`;
}

export function fmtTime(ts: number | null | undefined): string {
  if (ts == null) return "—";
  const d = new Date(ts * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

const AUTH_LABEL: Record<SolAuthority, string> = {
  RENOUNCED: "已放弃",
  NOT_RENOUNCED: "未放弃",
  UNKNOWN: "未检测",
  NOT_APPLICABLE: "不适用（非 SOL）",
};

function authTone(a: SolAuthority): string {
  if (a === "RENOUNCED") return "text-moss";
  if (a === "NOT_RENOUNCED") return "text-clay";
  return "text-muted";
}

function Stat({ label, value, tone, hint }: { label: string; value: ReactNode; tone?: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-line px-3 py-2" title={hint}>
      <p className="text-[11px] text-muted">{label}</p>
      <p className={`mt-0.5 font-mono text-sm ${tone ?? "text-fg"}`}>{value}</p>
    </div>
  );
}

function Section({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="mt-5">
      <h3 className="text-sm font-medium">{title}</h3>
      {note ? <p className="mt-0.5 text-xs text-muted">{note}</p> : null}
      <div className="mt-2">{children}</div>
    </section>
  );
}

const ENTRY_TONE: Record<BuyEntry["statusTone"], string> = {
  up: "text-moss",
  down: "text-clay",
  warn: "text-brass",
  muted: "text-muted",
};

/** Access Radar：这个代币在哪些平台可买 / 可达。库未初始化时整段隐藏；没有记录时只给一行安静的提示。 */
function BuyEntries({ chain, address }: { chain: string; address: string }) {
  const fn = useServerFn(fetchBuyEntries);
  const [entries, setEntries] = useState<BuyEntry[] | null>(null);

  useEffect(() => {
    let live = true;
    setEntries(null);
    fn({ data: { chain, address } })
      .then((res) => live && setEntries(res.initialized && !res.error ? res.entries : null))
      .catch(() => live && setEntries(null));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chain, address]);

  if (entries == null) return null;
  return (
    <Section title="买入入口" note={`Access Radar 记录的交易所 / 法币通道 / 链部署。时间 ${TZ_LABEL}；待确认 = 只按代号匹配。`}>
      {entries.length === 0 ? (
        <p className="text-xs text-muted">Access Radar 里还没有这个代币的入口记录</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted">
                <th className="py-1 text-left font-normal">平台</th>
                <th className="py-1 text-left font-normal">入口</th>
                <th className="py-1 text-left font-normal">状态</th>
                <th className="py-1 text-right font-normal">自</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.accessId} className="border-t border-line/50 align-top">
                  <td className="py-1">
                    <span>{e.platformName}</span>
                    <span className="ml-1 text-[10px] text-muted">{e.platformTypeLabel}</span>
                  </td>
                  <td className="py-1 font-mono">
                    {e.entryLabel}
                    {e.resolution.status !== "CONFIRMED" ? (
                      <span className="ml-1 text-[10px] text-brass" title={e.resolution.hint}>
                        {e.resolution.label}
                      </span>
                    ) : null}
                  </td>
                  <td className={`py-1 ${ENTRY_TONE[e.statusTone]}`}>
                    {e.statusLabel}
                    {e.provisional ? <span className="ml-1 text-[10px] text-brass">待确认</span> : null}
                    {e.warning ? (
                      <span className="ml-1 text-[10px] text-brass" title="交易所警示（유의 종목），仍可交易">
                        警示
                      </span>
                    ) : null}
                    {e.pendingRemovalAt ? (
                      <span className="ml-1 text-[10px] text-clay" title={fmtTs8Full(e.pendingRemovalAt)}>
                        {fmtTs8(e.pendingRemovalAt)} 下架
                      </span>
                    ) : null}
                  </td>
                  <td
                    className="py-1 text-right font-mono text-muted"
                    title={e.sinceIsBaseline ? "首次采集时就已存在，真实上线时间未知" : fmtTs8Full(e.statusSince)}
                  >
                    {e.sinceIsBaseline ? `≤${fmtTs8(e.statusSince)}` : fmtTs8(e.statusSince)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

export function TokenDetailDrawer({ chain, address, onClose }: { chain: string; address: string; onClose: () => void }) {
  const fn = useServerFn(fetchTokenDetail);
  const [data, setData] = useState<TokenDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    setData(null);
    setError("");
    fn({ data: { chain, address } })
      .then((res) => {
        if (!live) return;
        if (res.ok) setData(res);
        else setError(res.error);
      })
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [chain, address]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const r = data?.row;
  const d = r?.derived;
  const finals = data?.candles.filter((c) => c.status === "FINALIZED").slice(-14).reverse() ?? [];

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={onClose} role="presentation">
      <aside
        role="dialog"
        aria-label="代币详情"
        className="h-full w-full max-w-xl overflow-y-auto border-l border-line bg-bg p-4 sm:p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-mono text-xs text-brass">{chain.toUpperCase()}</p>
            <h2 className="truncate text-xl font-medium">{r?.symbol ?? (error ? "—" : "加载中…")}</h2>
            <p className="break-all font-mono text-[11px] text-muted">{address}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="关闭" className="inline-flex size-9 shrink-0 items-center justify-center rounded-full border border-line hover:bg-surface-2">
            <X className="size-4" />
          </button>
        </div>

        {error ? <p className="mt-4 rounded-lg border border-clay/30 bg-clay/10 p-3 text-sm text-clay">{error}</p> : null}

        {r && d ? (
          <>
            <Section title="行情" note="GMGN 原始字段。— = 未观察到；0 是真实 0。">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <Stat label="价格" value={r.price == null ? "—" : `$${fmtNum(r.price)}`} />
                <Stat label="1h 涨跌" value={fmtPctPoints(r.pc1h)} tone={pctTone(r.pc1h)} />
                <Stat
                  label={`24h 涨跌${r.pcInterval ? "" : "（窗口未确认）"}`}
                  value={fmtPctPoints(r.pc24h ?? r.pcRaw)}
                  tone={pctTone(r.pc24h ?? r.pcRaw)}
                  hint={r.pcInterval ? "Trending --interval 24h" : `来源 ${r.pcRawSource ?? "legacy"}，窗口未确认，不参与计算`}
                />
                <Stat label="24h 成交额" value={fmtUsdN(r.volume24h)} />
                <Stat label="FDV" value={fmtUsdN(r.fdv)} hint="GMGN market_cap = price × total_supply" />
                <Stat label="持币地址" value={r.holders == null ? "—" : r.holders.toLocaleString()} hint="当前持币地址数，不是交易者数" />
                <Stat label="24h 买入笔数" value={r.buys24h == null ? "—" : r.buys24h.toLocaleString()} tone="text-moss" />
                <Stat label="24h 卖出笔数" value={r.sells24h == null ? "—" : r.sells24h.toLocaleString()} tone="text-clay" />
                <Stat label="24h 交易笔数" value={r.swaps24h == null ? "—" : r.swaps24h.toLocaleString()} />
              </div>
            </Section>

            <Section title="名次" note="名次只在同一 endpoint + 请求参数内可比。不在榜 = —，不是 0。">
              <div className="grid grid-cols-2 gap-2">
                <Stat label={`Trending ${r.trendingRankContext ?? ""}`} value={r.trendingRank == null ? "—" : `#${r.trendingRank}`} hint={fmtTime(r.trendingRankAt)} />
                <Stat label={`Hot ${r.hotRankContext ?? ""}`} value={r.hotRank == null ? "—" : `#${r.hotRank}`} hint={fmtTime(r.hotRankAt)} />
              </div>
            </Section>

            <Section title="Signal" note="只展示触发时间与触发时市值（FDV 口径）。">
              {data!.signals.length === 0 ? (
                <p className="text-xs text-muted">最近 24 小时没有信号</p>
              ) : (
                <ul className="space-y-1 font-mono text-xs">
                  {data!.signals.slice(0, 5).map((s) => (
                    <li key={s.seenAt} className="flex justify-between border-b border-line/50 py-1">
                      <span>{fmtTime(s.triggerAt)}</span>
                      <span>{fmtUsdN(s.triggerMc)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title="SOL 权限" note="只在 SOL 上有意义；EVM 显示不适用。">
              <div className="grid grid-cols-2 gap-2">
                <Stat label="Mint 权限" value={AUTH_LABEL[r.solMintAuthority]} tone={authTone(r.solMintAuthority)} />
                <Stat label="Freeze 权限" value={AUTH_LABEL[r.solFreezeAuthority]} tone={authTone(r.solFreezeAuthority)} />
              </div>
            </Section>

            <Section title="本地计算指标" note="DERIVED：由上面的字段在本地计算，不是 GMGN 字段。">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <Stat label="买入笔数占比" value={d.buySellRatio == null ? "—" : `${(d.buySellRatio * 100).toFixed(0)}%`} />
                <Stat label="买入笔数 1h 倍数" value={fmtX(d.buysAccel1h)} hint={d.activityContext ?? undefined} />
                <Stat label="卖出笔数 1h 倍数" value={fmtX(d.sellsAccel1h)} />
                <Stat label="交易笔数 1h 倍数" value={fmtX(d.swapsAccel1h)} />
                <Stat label="成交额 1h 倍数" value={fmtX(d.volumeAccel1h)} />
                <Stat label="价格加速度" value={d.priceAccel == null ? "—" : `${d.priceAccel.toFixed(1)} pp`} hint="pc1h − pc24h / 24" />
                <Stat label="Trending 名次 1h" value={d.trendingNewEntry ? "新进榜" : d.trendingRankMove1h == null ? "—" : `${d.trendingRankMove1h > 0 ? "↑" : d.trendingRankMove1h < 0 ? "↓" : ""}${Math.abs(d.trendingRankMove1h)}`} />
                <Stat label="成交额 / FDV" value={fmtX(d.volumeToFdv)} />
                <Stat label="日成交额 / 前7日" value={fmtX(d.dailyVolumeAccel)} hint="只用已定稿日K" />
                <Stat label="突破前7日最高" value={d.breakout7d == null ? "—" : d.breakout7d ? "是" : "否"} tone={d.breakout7d ? "text-moss" : undefined} />
                <Stat label="连涨（已定稿）" value={r.streak == null ? "—" : `${r.streak}D`} />
                <Stat label={`${r.changeDays}日累计`} value={r.changeNd == null ? "—" : fmtPctPoints(r.changeNd * 100)} tone={pctTone(r.changeNd)} />
              </div>
              <p className="mt-2 text-xs text-muted">
                爆款分 {r.score.score} / 已评估 {r.score.evaluated}
                {r.score.reasons.length ? ` · ${r.score.reasons.join(" · ")}` : ""}
              </p>
            </Section>

            <Section title="已定稿日 K（最近 14 根）" note="只列 FINALIZED。成交额单位 USD。">
              {finals.length === 0 ? (
                <p className="text-xs text-muted">没有已定稿日 K</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full font-mono text-xs">
                    <thead>
                      <tr className="text-muted">
                        <th className="py-1 text-left font-normal">UTC 日</th>
                        <th className="py-1 text-right font-normal">开</th>
                        <th className="py-1 text-right font-normal">高</th>
                        <th className="py-1 text-right font-normal">低</th>
                        <th className="py-1 text-right font-normal">收</th>
                        <th className="py-1 text-right font-normal">成交额</th>
                      </tr>
                    </thead>
                    <tbody>
                      {finals.map((c) => (
                        <tr key={c.ts} className="border-t border-line/50">
                          <td className="py-1">{new Date(c.ts * 1000).toISOString().slice(0, 10)}</td>
                          <td className="py-1 text-right">{fmtNum(c.open)}</td>
                          <td className="py-1 text-right">{fmtNum(c.high)}</td>
                          <td className="py-1 text-right">{fmtNum(c.low)}</td>
                          <td className="py-1 text-right">{fmtNum(c.close)}</td>
                          <td className="py-1 text-right">{fmtUsdN(c.volume)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Section>
          </>
        ) : null}

        <BuyEntries chain={chain} address={address} />
      </aside>
    </div>
  );
}
