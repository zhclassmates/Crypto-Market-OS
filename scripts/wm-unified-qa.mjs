import { DatabaseSync } from "node:sqlite";
import { queryUnified } from "../src/lib/rh/wm-unified-query.ts";
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";
const url = process.argv[2] || "http://127.0.0.1:8080/#sec-market";
const label = process.argv[3] || "dev";
// Read current persisted data; old V1.5 reports predate the GMGN expansion.
const db = new DatabaseSync(process.env.WM_MARKET_DB ||
  "/Users/zhaomosheng/Desktop/world-model-os-v1/data/world_model_market.sqlite", { readOnly: true });
const expected = { unique_assets: Number(db.prepare("SELECT COUNT(*) n FROM wm_unified_current").get().n) };
const readPage = (query) => queryUnified(db, query);
const initial = readPage({ sort: "market_cap", direction: "desc" });
const b = await chromium.launch({ headless: true });
const p = await b.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [],
  failed = [],
  checks = [];
p.on("console", (m) => {
  if (m.type() === "error") errors.push(m.text());
});
p.on("pageerror", (e) => errors.push(String(e)));
p.on("requestfailed", (r) => failed.push({ url: r.url(), error: r.failure()?.errorText }));
try {
  await p.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
  const section = p.locator("[data-unified-market]");
  await section.locator("[data-unified-asset]").first().waitFor({ timeout: 60000 });
  const firstRows = await section
    .locator("[data-unified-asset]")
    .evaluateAll((rr) => rr.map((r) => r.getAttribute("data-unified-asset")));
  if (firstRows.length !== 50) throw Error("Not 50 server-paged records");
  checks.push("50 real unified records");
  if (JSON.stringify(firstRows) !== JSON.stringify(initial.rows.map(r => r.canonical_asset_id)))
    throw Error("Default all-market page differs from database query");
  checks.push("default all collected assets matches live SQLite");
  const content = await section.innerText();
  if (
    !content.includes(expected.unique_assets.toLocaleString("en-US")) ||
    !content.includes("18,235") ||
    !content.includes("8,141")
  )
    throw Error("Wrong counts");
  checks.push("actual source/asset counters");
  const defaults=db.prepare("SELECT u.canonical_asset_id FROM wm_unified_sources s JOIN wm_unified_current u USING(canonical_asset_id) WHERE s.provider='cg' AND s.provider_id IN ('bitcoin','ethereum','solana') AND u.identity_confidence='VERIFIED_MAPPING'").all().map(r=>r.canonical_asset_id);
  await p.waitForFunction(ids=>ids.every(id=>JSON.parse(localStorage.getItem('market_watchlist_v1')||'[]').some(w=>w.chain==='unified'&&w.address===id)),defaults);
  if(defaults.length!==3) throw Error('Native default watch missing');
  checks.push('BTC / ETH / SOL default watch without restricting all assets');
  await section.evaluate((el) => el.scrollIntoView({ block: "start" }));
  await p.screenshot({ path: `screenshots/wm-unified-${label}-table.png` });
  await section.getByRole("button", { name: "下一页", exact: true }).click();
  await p.waitForFunction(
    (id) =>
      document.querySelector("[data-unified-asset]")?.getAttribute("data-unified-asset") !== id,
    firstRows[0],
  );
  const secondRows = await section
    .locator("[data-unified-asset]")
    .evaluateAll((rr) => rr.map((r) => r.getAttribute("data-unified-asset")));
  if (secondRows.some((id) => firstRows.includes(id))) throw Error("Pagination duplicated records");
  checks.push("pagination changes database page");
  async function expectPage(query) {
    const expectedIds = readPage(query).rows.map(r => r.canonical_asset_id);
    await p.waitForFunction(ids => {
      const el = document.querySelector("[data-unified-market]");
      return el?.getAttribute("aria-busy") === "false" &&
        JSON.stringify([...el.querySelectorAll("[data-unified-asset]")].map(r => r.getAttribute("data-unified-asset"))) === JSON.stringify(ids);
    }, expectedIds, { timeout: 45000 });
  }
  await section.getByLabel("统一质量筛选").selectOption("");
  await section.getByLabel("统一来源筛选").selectOption("gmgn");
  await expectPage({source:"gmgn", sort:"market_cap", direction:"desc"});
  checks.push("GMGN filter matches database page");
  await section.getByLabel("统一来源筛选").selectOption("dex");
  await expectPage({source:"dex", sort:"market_cap", direction:"desc"});
  checks.push("DEX filter includes retained auxiliary records");
  await section.getByLabel("统一市场搜索").fill("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48");
  await p.waitForFunction(() => document.querySelectorAll("[data-unified-asset]").length === 1);
  checks.push("contract search");
  const row = section.locator("[data-unified-asset]").first();
  const id = await row.getAttribute("data-unified-asset");
  await row.locator("td").first().locator("button").first().click();
  const dialog = p.getByRole("dialog", { name: "统一资产详情" });
  await dialog.getByText("字段采用结果与理由", { exact: true }).waitFor();
  const detailText = await dialog.innerText();
  if (!detailText.includes("cg:") || !detailText.includes("dex:"))
    throw Error("Missing source provenance");
  checks.push("detail retains CG and DEX source provenance");
  await p.screenshot({ path: `screenshots/wm-unified-${label}-detail.png` });
  await dialog.getByLabel("关闭统一详情").click();
  await row.getByRole("button", { name: /星标/ }).click();
  await section.getByRole("button", { name: "星标", exact: true }).click();
  await p.waitForTimeout(500);
  if ((await section.locator("[data-unified-asset]").count()) !== 1)
    throw Error("watch filter lost starred asset");
  checks.push("star and watch filter");
  await row.getByRole("button", { name: /隐藏/ }).click();
  await p.waitForFunction(() => document.querySelectorAll("[data-unified-asset]").length === 0);
  checks.push("hide preference excludes before pagination");
  await section.getByLabel("隐藏代币筛选").selectOption("only");
  await p.waitForFunction(() => document.querySelectorAll("[data-unified-asset]").length === 1);
  await p.reload({waitUntil:'domcontentloaded'});
  await section.locator('[data-unified-asset]').first().waitFor();
  // Restore the exact persisted hidden identity, independent of search aliases.
  await section.getByLabel('统一市场搜索').fill(id);
  await section.getByLabel('隐藏代币筛选').selectOption('only');
  await expectPage({search:id,onlyHiddenKeys:['unified:'+id]});
  await section.locator('[data-unified-asset]').first().getByRole('button',{name:/恢复/}).click();
  await expectPage({search:id,onlyHiddenKeys:[]});
  checks.push('hidden preference survives reload and individual restore');
  await section.getByLabel('隐藏代币筛选').selectOption('exclude');
  await expectPage({search:id});
  await section.getByRole("button", { name: /恢复本机隐藏/ }).count();
  await row.getByRole("button", { name: /星标/ }).click();

  await section.getByLabel("统一市场搜索").fill("");
  await section.getByLabel("统一来源筛选").selectOption("");
  await p.waitForFunction(() => document.querySelectorAll("[data-unified-asset]").length === 50);
  for(const search of ['Bitcoin','BTC']) {
    await section.getByLabel('统一市场搜索').fill(search);
    await expectPage({search,sort:'market_cap',direction:'desc'});
  }
  checks.push('name and symbol search across all matching contracts');
  const nativeId=db.prepare("SELECT canonical_asset_id FROM wm_unified_sources WHERE provider='cg' AND provider_id='bitcoin'").get().canonical_asset_id;
  await section.getByLabel('统一市场搜索').fill(nativeId);
  await expectPage({search:nativeId,sort:'market_cap',direction:'desc'});
  const nativeRow=section.locator(`[data-unified-asset="${nativeId}"]`);
  await nativeRow.getByRole('button',{name:/星标/}).click();
  await p.reload({waitUntil:'domcontentloaded'});
  await section.locator('[data-unified-asset]').first().waitFor();
  await section.getByLabel('统一市场搜索').fill(nativeId);
  await expectPage({search:nativeId,sort:'market_cap',direction:'desc'});
  if(await nativeRow.getByRole('button',{name:/星标/}).getAttribute('aria-pressed')!=='false') throw Error('Native unstar resurrected on reload');
  await nativeRow.getByRole('button',{name:/星标/}).click();
  checks.push('default native unstar remains persistent across reload');
  await section.getByLabel('统一市场搜索').fill('');
  await expectPage({sort:'market_cap',direction:'desc'});
  for (const tier of ['NEW','EARLY','MAIN']) {
    await section.getByLabel('统一分层筛选').selectOption(tier);
    await expectPage({tier,sort:'market_cap',direction:'desc'});
  }
  checks.push('NEW / EARLY / MAIN preserve existing tier rules');
  await section.getByLabel('统一分层筛选').selectOption('');
  await expectPage({sort:'market_cap',direction:'desc'});
  await section.locator('summary').click();
  await section.getByLabel('市值下限',{exact:true}).fill('1000000');
  await section.getByLabel('流动性下限',{exact:true}).fill('20000');
  await expectPage({minMarketCap:1000000,minLiquidity:20000,sort:'market_cap',direction:'desc'});
  checks.push('combined market-cap and liquidity range filter');
  await section.getByLabel('市值下限',{exact:true}).fill('');
  await section.getByLabel('流动性下限',{exact:true}).fill('');
  await expectPage({sort:'market_cap',direction:'desc'});
  const dates = readPage({}).dates;
  if (dates[6]>=new Date().toISOString().slice(0,10)) throw Error('Unclosed date header');
  checks.push('all seven headers are completed UTC natural days');
  const firstDate = dates[0], secondDate = dates[1];
  await section.locator(`[data-sort-date="${firstDate}"]`).click();
  await expectPage({dates:[{date:firstDate,direction:"desc"}],sort:"market_cap",direction:"desc"});
  await section.locator(`[data-sort-date="${secondDate}"]`).click();
  await expectPage({dates:[{date:secondDate,direction:"desc"},{date:firstDate,direction:"desc"}],sort:"market_cap",direction:"desc"});
  checks.push("whole-market most-recent-first multi-date ranking without Shift");
  await section.getByRole('button',{name:'下一页',exact:true}).click();
  await expectPage({page:2,dates:[{date:secondDate,direction:'desc'},{date:firstDate,direction:'desc'}],sort:'market_cap',direction:'desc'});
  await section.getByRole('button',{name:'上一页',exact:true}).click();
  await expectPage({dates:[{date:secondDate,direction:'desc'},{date:firstDate,direction:'desc'}],sort:'market_cap',direction:'desc'});
  checks.push('multi-date ranking retains correct page boundaries');
  await section.locator(`[data-sort-date="${secondDate}"]`).click();
  await expectPage({dates:[{date:secondDate,direction:"asc"},{date:firstDate,direction:"desc"}],sort:"market_cap",direction:"desc"});
  await section.locator(`[data-sort-date="${secondDate}"]`).click();
  await expectPage({dates:[{date:firstDate,direction:"desc"}],sort:"market_cap",direction:"desc"});
  checks.push('independent three-state date sorting');
  await section.locator(`[data-sort-date="${secondDate}"]`).click();
  await section.getByLabel(`${firstDate} 涨跌筛选`).selectOption("negative");
  await expectPage({dates:[{date:secondDate,direction:"desc"},{date:firstDate,direction:"desc"}],dailyFilters:[{date:firstDate,sign:"negative"}],sort:"market_cap",direction:"desc"});
  checks.push("negative daily return filter matches SQLite");
  await section.getByLabel(`${secondDate} 涨跌筛选`).selectOption('positive');
  await expectPage({dates:[{date:secondDate,direction:'desc'},{date:firstDate,direction:'desc'}],dailyFilters:[{date:firstDate,sign:'negative'},{date:secondDate,sign:'positive'}],sort:'market_cap',direction:'desc'});
  checks.push('multi-day AND filters remain separate from sorting');
  await section.getByRole("button", { name: "清除日期排序 / 筛选" }).click();
  await expectPage({sort:"market_cap",direction:"desc"});
  await section.getByLabel("统一质量筛选").selectOption("VALID");
  for (const [chain, name] of [["bitcoin", "Bitcoin"], ["ethereum", "Ethereum"], ["solana", "Solana"]]) {
    await section.getByLabel("统一链筛选").selectOption(chain);
    await expectPage({chain,quality:"VALID",sort:"market_cap",direction:"desc"});
    const native = readPage({chain,quality:"VALID",sort:"market_cap",direction:"desc"}).rows.find(r => r.name === name && r.identity_confidence === "VERIFIED_MAPPING");
    if (!native) throw Error(`${name} absent from current-quote VALID gate`);
    checks.push(`native ${name} remains VALID despite missing seven-day history`);
  }
  await section.getByLabel("统一链筛选").selectOption("");
  await section.getByLabel("统一质量筛选").selectOption("");
  await expectPage({sort:"market_cap",direction:"desc"});
  await p.setViewportSize({ width: 390, height: 844 });
  await section.evaluate((el) => el.scrollIntoView({ block: "start" }));
  await p.screenshot({ path: `screenshots/wm-unified-${label}-table-mobile.png` });
  const scroll=section.locator('[data-unified-scroll]');
  const fixedBefore=await section.locator('tbody tr').first().locator('td').first().boundingBox();
  await scroll.evaluate(el=>{el.scrollLeft=800;});
  const fixedAfter=await section.locator('tbody tr').first().locator('td').first().boundingBox();
  if (Math.abs(fixedBefore.x-fixedAfter.x)>1) throw Error('Token column not fixed');
  const starX=await section.locator('tbody tr').first().locator('td').nth(1).boundingBox();
  if (Math.abs(starX.x-(fixedAfter.x+fixedAfter.width))>2) throw Error('Star column not fixed alongside token');
  checks.push('Token and Star fixed during horizontal mobile scroll');
  // Scroll the viewport to the scroller, not the very wide thead: native
  // scrollIntoView also moves horizontal ancestors and can capture mid-paint.
  await scroll.evaluate(el=>window.scrollTo(0,window.scrollY+el.getBoundingClientRect().top));
  await p.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  await p.screenshot({path:`screenshots/wm-unified-${label}-table-mobile-scroll.png`});
  const overflow = await p.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
  if (overflow) throw Error("mobile page overflow");
  checks.push("mobile content with contained table scrolling");
  if (errors.length) throw Error("Browser console/page errors: " + errors.join("; "));
  const result = {
    ok: true,
    url,
    checks,
    errors,
    failed,
    firstAsset: firstRows[0],
    searchedAsset: id,
    visibleRows: await section.locator("[data-unified-asset]").count(),
  };
  writeFileSync(`integration/unified-market/qa-${label}.json`, JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  console.error(JSON.stringify({error:String(error),input:await p.getByLabel("统一市场搜索").inputValue().catch(()=>""),actualIds:await p.locator("[data-unified-asset]").evaluateAll(rows=>rows.map(r=>r.getAttribute("data-unified-asset"))),errors,failed,checks,body:await p.locator("body").innerText().catch(()=>"")},null,2));
  await p.screenshot({path:`screenshots/wm-unified-${label}-failure.png`}).catch(()=>{});
  throw error;
} finally {
  await b.close();
  db.close();
}
