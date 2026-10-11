import config from "../../../market-chains.json" with { type: "json" };

export const MARKET_CHAINS = config.chains.map((chain) => chain.id);
export const MARKET_CHAIN_TABS = ["all", ...MARKET_CHAINS];
export const MARKET_CHAIN_LABEL: Record<string, string> = Object.fromEntries([
  ["all", "全部"],
  ...config.chains.map((chain) => [chain.id, chain.label]),
]);

// Access Radar 用小写规范链名（access_radar/adapters/chains.py：solana / ethereum / bsc ...）。
// market-chains.json 每条链的 access 列表第一个是规范名，其余是别名；不在表里的链没有 GMGN 行情。
const accessRows = config.chains as { id: string; access?: string[] }[];
export const ACCESS_CHAIN_TO_MARKET: Record<string, string> = Object.fromEntries(
  accessRows.flatMap((chain) => (chain.access ?? []).map((name) => [name.toLowerCase(), chain.id])),
);
export const MARKET_TO_ACCESS_CHAINS: Record<string, string[]> = Object.fromEntries(
  accessRows.map((chain) => [chain.id, (chain.access ?? []).map((name) => name.toLowerCase())]),
);
