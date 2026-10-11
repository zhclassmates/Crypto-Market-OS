import { useEffect, useMemo, useState } from "react";
import { ExternalLink, X } from "lucide-react";
import {
  isSafeSourceUrl,
  isScheduledAccessEvent,
  isSurpriseAccessEvent,
  matchesAccessCategory,
  sortAccessEvents,
  type MarketAccessEvent,
} from "@/lib/rh/market-access";

function compactAddress(address: string): string {
  if (address.length <= 12) return address;
  return `${address.slice(0, 6)}…${address.slice(-4)}`;
}

function formatTimestamp(timestamp: number | undefined): string {
  if (timestamp == null || !Number.isFinite(timestamp)) return "尚未记录时间";
  const date = new Date(timestamp * 1000);
  const part = (value: number) => String(value).padStart(2, "0");
  return `${part(date.getMonth() + 1)}/${part(date.getDate())} ${part(date.getHours())}:${part(date.getMinutes())}`;
}

function formatFullTimestamp(timestamp: number | undefined): string {
  if (timestamp == null || !Number.isFinite(timestamp)) return "—";
  const date = new Date(timestamp * 1000);
  const part = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${part(date.getMonth() + 1)}-${part(date.getDate())} ${part(date.getHours())}:${part(date.getMinutes())}:${part(date.getSeconds())}`;
}

function formatDuration(seconds: number): string {
  const sign = seconds < 0 ? "−" : "";
  const value = Math.abs(seconds);
  if (value < 60) return `${sign}${value}s`;
  if (value < 3_600) return `${sign}${Math.floor(value / 60)}m ${value % 60}s`;
  return `${sign}${Math.floor(value / 3_600)}h ${Math.floor((value % 3_600) / 60)}m`;
}

function eventTitle(event: MarketAccessEvent): string {
  if (!event.label) return event.venue;
  return `${event.venue} · ${event.label}`;
}

const OTHER_VENUES = [
  {
    label: "Binance Futures",
    observed: (events: readonly MarketAccessEvent[]) => events.some((event) => event.kind === "BINANCE_FUTURES"),
  },
  {
    label: "Binance Spot",
    observed: (events: readonly MarketAccessEvent[]) => events.some((event) => event.kind === "BINANCE_SPOT"),
  },
  {
    label: "Coinbase",
    observed: (events: readonly MarketAccessEvent[]) => events.some((event) => matchesAccessCategory(event, "coinbase")),
  },
  {
    label: "Upbit",
    observed: (events: readonly MarketAccessEvent[]) => events.some((event) => matchesAccessCategory(event, "upbit")),
  },
  {
    label: "Robinhood",
    observed: (events: readonly MarketAccessEvent[]) => events.some((event) => event.kind === "ROBINHOOD"),
  },
] as const;

export interface MarketAccessDrawerDetail {
  chain: string;
  address: string;
  symbol: string | null;
  events: MarketAccessEvent[];
}

export function MarketAccessDrawer({
  detail,
  onClose,
}: {
  detail: MarketAccessDrawerDetail;
  onClose: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const timeline = useMemo(() => {
    const ordered = sortAccessEvents(detail.events);
    const timed = ordered.filter((event) => Number.isFinite(event.detectedAt)).reverse();
    const untimed = ordered.filter((event) => !Number.isFinite(event.detectedAt));
    return [...timed, ...untimed];
  }, [detail.events]);
  const otherVenues = OTHER_VENUES.filter((venue) => !venue.observed(detail.events));

  useEffect(() => {
    setSelectedId(null);
  }, [detail.chain, detail.address]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-overlay/40 backdrop-blur-sm" onClick={onClose} role="presentation">
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="市场准入状态"
        className="h-full w-full max-w-lg overflow-y-auto border-l border-line bg-bg p-4 sm:p-6"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-line pb-4">
          <div className="min-w-0">
            <p className="font-mono text-xs text-primary">{detail.chain.toUpperCase()}</p>
            <h2 className="truncate text-xl font-medium">{detail.symbol || "?"}</h2>
            <p className="font-mono text-xs text-muted" title={detail.address}>{compactAddress(detail.address)}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭市场准入状态"
            className="inline-flex size-10 shrink-0 items-center justify-center rounded-full border border-line hover:bg-surface-2"
          >
            <X className="size-4" />
          </button>
        </div>

        <section className="mt-5">
          <h3 className="text-base font-medium">市场准入状态</h3>
          <p className="mt-1 text-sm text-muted">该 Token 已观察到的交易所 / 市场准入记录</p>

          <ol className="mt-4">
            {timeline.map((event, index) => {
              const selected = selectedId === event.id;
              const hasDetails = event.detectedAt != null || event.receivedAt != null || event.sourceUrl != null;
              const feedAge = event.detectedAt != null && event.receivedAt != null
                ? event.receivedAt - event.detectedAt
                : null;
              return (
                <li key={event.id} className="relative pl-7">
                  {index < timeline.length - 1 ? (
                    <span className="absolute left-1.5 top-4 h-full w-px bg-line" aria-hidden="true" />
                  ) : null}
                  <span className="absolute left-0 top-3 size-3 rounded-full border-2 border-primary bg-bg" aria-hidden="true" />
                  <button
                    type="button"
                    onClick={() => hasDetails && setSelectedId((current) => current === event.id ? null : event.id)}
                    aria-expanded={hasDetails ? selected : undefined}
                    className="mb-3 min-h-11 w-full rounded-lg px-3 py-2 text-left hover:bg-surface"
                  >
                    <span className="block font-mono text-xs text-muted">{formatTimestamp(event.detectedAt)}</span>
                    <span className="mt-1 block text-sm text-fg">{eventTitle(event)}</span>
                    {isSurpriseAccessEvent(event) ? (
                      <span className="mt-1 inline-flex rounded-full border border-primary/35 bg-primary/10 px-2 py-0.5 font-mono text-[10px] text-primary">Surprise</span>
                    ) : null}
                    {isScheduledAccessEvent(event) ? (
                      <span className="mt-1 inline-flex rounded-full border border-line px-2 py-0.5 font-mono text-[10px] text-muted">Scheduled</span>
                    ) : null}
                  </button>

                  {selected ? (
                    <div className="mb-4 rounded-lg border border-line bg-surface px-3 py-3 text-xs">
                      <p className="font-medium text-fg">来源</p>
                      {isSafeSourceUrl(event.sourceUrl) ? (
                        <a
                          href={event.sourceUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-2 inline-flex min-h-10 items-center gap-1.5 text-primary hover:underline"
                        >
                          查看原始公告
                          <ExternalLink className="size-3" />
                        </a>
                      ) : (
                        <p className="mt-2 text-muted">未提供安全的原始公告链接</p>
                      )}
                      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono text-[11px]">
                        <dt className="text-muted">Detected</dt>
                        <dd className="text-right text-fg">{formatFullTimestamp(event.detectedAt)}</dd>
                        <dt className="text-muted">Received</dt>
                        <dd className="text-right text-fg">{formatFullTimestamp(event.receivedAt)}</dd>
                        {feedAge != null ? (
                          <>
                            <dt className="text-muted">Feed age</dt>
                            <dd className="text-right text-fg">{formatDuration(feedAge)}</dd>
                          </>
                        ) : null}
                      </dl>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ol>
        </section>

        <section className="mt-6 border-t border-line pt-5">
          <h3 className="text-sm font-medium">其他场所</h3>
          <p className="mt-1 text-xs text-muted">仅表示当前系统没有记录到。</p>
          {otherVenues.length > 0 ? (
            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
              {otherVenues.map((venue) => (
                <li key={venue.label} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs text-muted">
                  <span className="size-2 shrink-0 rounded-full border border-muted" aria-hidden="true" />
                  <span>{venue.label} · 尚未记录</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-xs text-muted">所列场所均已有记录。</p>
          )}
        </section>
      </aside>
    </div>
  );
}
