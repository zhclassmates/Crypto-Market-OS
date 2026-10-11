/** 全市场（高召回扫描）专用：默认排序与全库搜索合并。不参与连涨榜任何计算。 */

/** "" / null / 非数字 → null；"0" → 0。 */
function numOrNull(v: string | number | null | undefined): number | null {
  if (v == null) return null;
  if (typeof v === "string" && v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export interface NewnessSortable {
  newnessAt?: number | null;
  volume24h: string;
  liquidityNum: number | null;
  liquidity: string;
}

/** 全市场默认排序：newness DESC → 24h volume DESC → liquidity DESC；每一级缺值都排后。 */
export function compareNewness(a: NewnessSortable, b: NewnessSortable): number {
  const keys = (t: NewnessSortable) => [
    t.newnessAt ?? null,
    numOrNull(t.volume24h),
    t.liquidityNum ?? numOrNull(t.liquidity),
  ];
  const ka = keys(a);
  const kb = keys(b);
  for (let i = 0; i < ka.length; i++) {
    const va = ka[i];
    const vb = kb[i];
    if (va == null && vb == null) continue;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (va !== vb) return vb - va;
  }
  return 0;
}

/** 全库搜索命中并进当前结果；同一 chain:address 以默认列表那份为准。 */
export function mergeSearchHits<T extends { chain: string; address: string }>(base: T[], hits: T[]): T[] {
  if (hits.length === 0) return base;
  const key = (t: T) => `${t.chain}:${t.address}`;
  const have = new Set(base.map(key));
  const extra = hits.filter((t) => !have.has(key(t)));
  return extra.length === 0 ? base : [...base, ...extra];
}
