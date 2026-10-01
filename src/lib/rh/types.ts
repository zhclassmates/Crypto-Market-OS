export type RungKey =
  | "onchain"
  | "aster"
  | "hl"
  | "bnAlpha"
  | "bnPerp"
  | "bnSpot"
  | "kr"
  | "rhQuoted"
  | "rhSpot";

export type Bar = {
  bar: number;
  w: number;
  label: string;
  lift?: number | null;
  note?: string;
};

export type Gate = {
  label: string;
  base: number;
  note: string;
  bars: Record<string, Bar>;
};

export type LadderToken = {
  symbol: string;
  address: string | null;
  kind: string;
  name: string;
  vol24h: number | null;
  liq: number | null;
  mcap: number | null;
  poolSeenAt: string | null;
  krVenue?: string | null;
  reached: Record<string, boolean>;
};

export type Candidate = {
  symbol: string;
  address: string;
  kind: string;
  gate: string;
  next: string;
  vol24h: number | null;
  liq: number | null;
  turn: number | null;
  raw: {
    liq: number | null;
    vol24h: number | null;
    mcap: number | null;
    ageD: number | null;
    holders: number | null;
    ct: number | null;
  };
  alphaPct?: { liq?: number | null; mcap?: number | null; vol?: number | null } | null;
  asterRule?: { mcapOk?: boolean | null; prereqOk?: boolean | null } | null;
  already?: string[];
};

export type VenueRule = {
  venue: string;
  kind: "published" | "published-vague" | "discretionary" | "none" | string;
  src: string;
  must: { k?: string; text: string }[];
  note?: string;
};

export type LadderSnapshot = {
  ts: number;
  coverage: { active: number; universe: number; volKnown?: number; liqKnown?: number };
  kinds: Record<string, number>;
  rungs: { key: string; track: string; prev: string | null; label: string; count: number; source: string }[];
  funnel: {
    key: string;
    count: number;
    conversionFromPrevPct: number;
    dropFromPrev: number;
    fromPrev: number;
  }[];
  gates: Record<string, Gate>;
  venueRules: Record<string, VenueRule>;
  listingHistory: {
    note: string;
    insight: string;
    pons: string;
    bnSpot: { n: number; detail: string };
    bnPerp: { n: number; detail: string };
    kr: { n: number; detail: string };
    coinbase: { n: number; detail: string };
  };
  alphaRef: {
    n: number;
    ageConversion: Record<string, { n: number; cex: number }>;
    rhOnAlpha: { symbol: string; at: number; score: number; cex: boolean; liq: number; holders: number; mcap: number }[];
  };
  advancedFeed: { symbol: string; kind: string; vol24h: number; stage: number; stageLabel: string; at: number }[];
  ruledOut: { symbol: string; vol24h: number; liq: number; why: string; all?: string[] }[];
  candidates: Candidate[];
  tokens: LadderToken[];
};

export type Part = {
  label: string;
  weight: number;
  raw: string;
  mapped: number | null;
};

export type Scored = {
  address: string;
  symbol: string;
  state: string;
  target: string;
  heat: number | null;
  quality: number | null;
  entry: number | null;
  listingP: string;
  listingBasis: string;
  venues: string;
  why: string[];
  liq: number;
  vol24: number;
  pc24: number;
  pc6: number;
  price: number;
  holders: number | null;
  volAccel: number | null;
  volLiq: number | null;
  holderG6: number | null;
  runup: number | null;
  nHist: number;
  heatParts: Part[];
  qualityParts: Part[];
  entryNotes: string[];
};

export type RateRow = {
  id: string;
  label: string;
  cells: { n: number | null; p: number | null; censored?: boolean }[];
};

export type DeskFrame = {
  hour: number;
  now: number;
  rows: Scored[];
  rates: RateRow[];
  history: Record<string, string[]>;
  alerts: string[];
};
