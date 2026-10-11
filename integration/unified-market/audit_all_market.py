"""Read-only delivery counts for the completed UTC window, not intraday coverage."""
import datetime as dt
import json
import sqlite3
from pathlib import Path
root=Path(__file__).resolve().parents[2]
core=Path(json.loads((Path(__file__).parent/'install-manifest.json').read_text())['target'])
db=sqlite3.connect(core.joinpath('data/world_model_market.sqlite').as_uri()+'?mode=ro',uri=True)
db.row_factory=sqlite3.Row;db.execute('BEGIN')
end=dt.datetime.now(dt.timezone.utc).date()-dt.timedelta(days=1);start=end-dt.timedelta(days=6)
def scalar(sql,*args): return db.execute(sql,args).fetchone()[0]
result={
 'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),
 'version':scalar("SELECT value FROM wm_unified_meta WHERE key='version'"),
 'synced_at':scalar("SELECT value FROM wm_unified_meta WHERE key='synced_at'"),
 'unique_assets':scalar('SELECT COUNT(*) FROM wm_unified_current'),
 'source_coverage':[dict(r) for r in db.execute('SELECT provider,COUNT(*) records,COUNT(DISTINCT canonical_asset_id) assets FROM wm_unified_sources GROUP BY provider')],
 'onchain_audit':json.loads(scalar("SELECT value FROM wm_unified_meta WHERE key='onchain_audit'")),
 'quality':dict(db.execute('SELECT quality_status,COUNT(*) FROM wm_unified_current GROUP BY quality_status')),
 'tiers':dict(db.execute('SELECT market_tier,COUNT(*) FROM wm_unified_current GROUP BY market_tier')),
 'unresolved':scalar("SELECT COUNT(*) FROM wm_unified_current WHERE identity_confidence='UNRESOLVED'"),
 'completed_window':[str(start),str(end)],
 'finalized_price_assets':scalar("SELECT COUNT(DISTINCT canonical_asset_id) FROM wm_unified_daily WHERE time_basis='utc_finalized' AND date_utc BETWEEN ? AND ?",str(start),str(end)),
 'valid_daily_return_assets':scalar("SELECT COUNT(DISTINCT canonical_asset_id) FROM wm_unified_daily WHERE time_basis='utc_finalized' AND return_quality='VALID' AND daily_return IS NOT NULL AND date_utc BETWEEN ? AND ?",str(start),str(end)),
 'seven_valid_daily_returns_assets':scalar("SELECT COUNT(*) FROM (SELECT canonical_asset_id FROM wm_unified_daily WHERE time_basis='utc_finalized' AND return_quality='VALID' AND daily_return IS NOT NULL AND date_utc BETWEEN ? AND ? GROUP BY canonical_asset_id HAVING COUNT(*)=7)",str(start),str(end)),
 'quotes_missing':scalar('SELECT COUNT(*) FROM wm_unified_current WHERE price_usd IS NULL'),
 'quotes_over_24h':scalar("SELECT COUNT(*) FROM wm_unified_current WHERE data_timestamp IS NOT NULL AND julianday(data_timestamp)<julianday('now','-1 day')"),
 'quality_reports':[dict(r) for r in db.execute('SELECT provider,status,date_utc,checked_at_utc FROM wm_quality_reports ORDER BY checked_at_utc DESC LIMIT 3')],
 'native_assets':[dict(r) for r in db.execute("SELECT canonical_asset_id,name,quality_status,missing_fields,data_timestamp FROM wm_unified_current WHERE identity_confidence='VERIFIED_MAPPING'")],
}
db.rollback();db.close()
source=sqlite3.connect(root.joinpath('rh_v2/market.sqlite').as_uri()+'?mode=ro',uri=True)
source.row_factory=sqlite3.Row
# Only health classification evidence; do not copy upstream request/error payloads.
result['source_health']=[dict(r) for r in source.execute("SELECT chain,source,last_success,last_attempt,consecutive_errors FROM source_health WHERE source='gmgn_hot' ORDER BY chain")]
source.close()
(root/'backups/all-market-20261011/data-audit.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
print(json.dumps({k:v for k,v in result.items() if k not in ('onchain_audit','native_assets','source_health','quality_reports')},ensure_ascii=False,indent=2))
