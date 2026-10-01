export function usd(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const sign = v < 0 ? "−" : "";
  const n = Math.abs(v);
  if (n >= 1e9) return `${sign}$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${sign}$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${sign}$${(n / 1e3).toFixed(n >= 1e4 ? 0 : 1)}k`;
  return `${sign}$${n.toFixed(0)}`;
}

export function pct(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const n = v.toFixed(digits);
  return `${v > 0 ? "+" : ""}${n}%`;
}

export function num(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return "–";
  return v.toFixed(digits);
}

export function stamp(ms: number): string {
  const d = new Date(ms);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`;
}

export function shortAddr(a: string | null | undefined): string {
  if (!a) return "–";
  return `${a.slice(0, 6)}…${a.slice(-4)}`;
}

export function turn(vol: number | null | undefined, liq: number | null | undefined): number | null {
  if (!vol || !liq) return null;
  return vol / liq;
}

const KIND: Record<string, string> = {
  stock: "链上美股",
  paired: "与股票配对",
  meme: "纯 Meme",
  eco: "生态币",
  mirror: "仿股票",
};

export function kindLabel(k: string): string {
  return KIND[k] ?? k;
}
