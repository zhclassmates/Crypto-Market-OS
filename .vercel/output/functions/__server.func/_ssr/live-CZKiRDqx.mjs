import { n as TSS_SERVER_FUNCTION, t as createServerFn } from "./ssr.mjs";
//#region node_modules/.nitro/vite/services/ssr/assets/live-CZKiRDqx.js
var createServerRpc = (serverFnMeta, splitImportFn) => {
	const url = "/_serverFn/" + serverFnMeta.id;
	return Object.assign(splitImportFn, {
		url,
		serverFnMeta,
		[TSS_SERVER_FUNCTION]: true
	});
};
var fetchRhAlpha_createServerFn_handler = createServerRpc({
	id: "bc3f91d7c0778e85c67439c36f78c8c78f9ab59bea52d7ae0e460d42cbf63b75",
	name: "fetchRhAlpha",
	filename: "src/lib/rh/live.ts"
}, (opts) => fetchRhAlpha.__executeServer(opts));
var fetchRhAlpha = createServerFn({ method: "GET" }).handler(fetchRhAlpha_createServerFn_handler, async () => {
	try {
		const res = await fetch("https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list", { headers: {
			Accept: "application/json",
			"User-Agent": "rh-ladder/1.0"
		} });
		if (!res.ok) return {
			ok: false,
			error: `币安返回 ${res.status}`
		};
		const body = await res.json();
		const tokens = [];
		for (const t of body.data ?? []) {
			if (String(t.chainId ?? "") !== "4663") continue;
			if (t.offline || t.offsell) continue;
			const address = (t.contractAddress || "").toLowerCase();
			if (!address.startsWith("0x") || address.length !== 42) continue;
			tokens.push({
				symbol: (t.symbol || "").toUpperCase(),
				address,
				listingTime: typeof t.listingTime === "number" ? t.listingTime : null
			});
		}
		tokens.sort((a, b) => (b.listingTime ?? 0) - (a.listingTime ?? 0));
		return {
			ok: true,
			n: tokens.length,
			fetchedAt: Date.now(),
			tokens
		};
	} catch (e) {
		return {
			ok: false,
			error: e instanceof Error ? e.message : "拉不到币安 Alpha"
		};
	}
});
//#endregion
export { fetchRhAlpha_createServerFn_handler };
