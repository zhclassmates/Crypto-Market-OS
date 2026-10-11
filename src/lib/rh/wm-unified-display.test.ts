import assert from "node:assert/strict";
import { test } from "node:test";
import { cycleDateSort,completedUtcWindow,historyGapLabel,seedDefaultWatch, formatUnifiedDailyReturn } from "./wm-unified-display.ts";
test("unified UTC daily percentage points retain their scale in the existing UI", () => {
  assert.equal(formatUnifiedDailyReturn(12.5), "+12.5%");
  assert.equal(formatUnifiedDailyReturn(-1.5), "−1.5%");
  assert.equal(formatUnifiedDailyReturn(0), "0.0%");
  assert.equal(formatUnifiedDailyReturn(null), "—");
  assert.equal(formatUnifiedDailyReturn(undefined), "—");
});

test("recent click has highest priority without shift and each date cycles independently",()=>{
  let dates=cycleDateSort([],'2026-10-09');
  dates=cycleDateSort(dates,'2026-10-10');
  assert.deepEqual(dates.map(d=>d.date),['2026-10-10','2026-10-09']);
  dates=cycleDateSort(dates,'2026-10-09');
  assert.equal(dates[0].direction,'asc');
  dates=cycleDateSort(dates,'2026-10-09');
  assert.deepEqual(dates,[{date:'2026-10-10',direction:'desc'}]);
});
test("seven completed natural UTC days roll over at midnight",()=>{
  assert.deepEqual(completedUtcWindow(new Date('2026-11-01T00:00:00Z')),['2026-10-25','2026-10-26','2026-10-27','2026-10-28','2026-10-29','2026-10-30','2026-10-31']);
  assert.match(historyGapLabel('2026-10-10','2026-10-09'),/未收录/);
  assert.match(historyGapLabel(null,'2026-10-09'),/历史缺口/);
});
test("native default watch adds once, preserves prior preferences and unstar on reload",()=>{
  const map=new Map<string,string>();const storage={getItem:(k:string)=>map.get(k)??null,setItem:(k:string,v:string)=>{map.set(k,v)}};
  storage.setItem('market_watchlist_v1',JSON.stringify([{chain:'base',address:'0x1',symbol:'X',name:'X',addedAt:1}]));
  const defaults=['bitcoin','ethereum','solana'].map(id=>({canonical_asset_id:id,name:id,symbol:id}));
  assert.equal(seedDefaultWatch(storage,defaults,2),true);
  assert.equal(JSON.parse(storage.getItem('market_watchlist_v1')!).length,4);
  storage.setItem('market_watchlist_v1','[]');
  assert.equal(seedDefaultWatch(storage,defaults,3),false);
  assert.equal(storage.getItem('market_watchlist_v1'),'[]');
});
