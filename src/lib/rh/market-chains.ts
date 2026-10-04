import config from "../../../market-chains.json" with { type: "json" };

export const MARKET_CHAINS = config.chains.map((chain) => chain.id);
export const MARKET_CHAIN_TABS = ["all", ...MARKET_CHAINS];
export const MARKET_CHAIN_LABEL: Record<string, string> = Object.fromEntries([
  ["all", "全部"],
  ...config.chains.map((chain) => [chain.id, chain.label]),
]);
