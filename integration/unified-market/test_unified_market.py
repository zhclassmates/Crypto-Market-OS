import json,sqlite3,sys,unittest,socket
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
project=Path(__file__).parents[1]
if not (project/'market_ingest.py').exists():project=Path(__file__).parents[3]/'world-model-os-v1'
sys.path.insert(0,str(project))
import market_ingest as ingest
import market_quality as quality
sys.path.insert(0,str(Path(__file__).parent))
import unified_market as u
A='0x'+'a'*40;B='0x'+'b'*40
class UnifiedTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:');ingest.schema(self.c);quality.schema(self.c)
  for p in ['cg','cmc','dex']:
   self.c.execute('INSERT INTO wm_quality_reports VALUES(?,?,?,?,?,?,?,?)',(p,p,'2026-10-10','2026-10-10T12:00:00+00:00','trusted','{}','[]','[]'))
  self.c.commit();self.addCleanup(self.c.close)
 def add(self,p,id,addr=A,chain='ethereum',day='2026-10-10',price=1,cap=100,vol=10,liq=None,basis='intraday'):
  ingest.record(self.c,p,id,'SAME','Same',day,price,vol,'rolling_24h',cap=cap,liq=liq,chain=chain,address=addr,time_basis=basis,market_scope='aggregated' if p!='dex' else 'onchain_returned_pools')
  self.c.execute('UPDATE wm_market_observations SET collected_at_utc=? WHERE provider=? AND provider_id=? AND date_utc=?',(day+'T12:00:00+00:00',p,id,day));self.c.commit()
 def run_sync(self):return u.sync(self.c)
 def rows(self):return [dict(r) for r in self.c.execute('SELECT * FROM wm_unified_current')]
 def test_contract_cross_source(self):
  self.add('cg','one');self.add('cmc','1',addr=A.upper());s=self.run_sync();self.assertEqual(s['unique_assets'],1);self.assertEqual(s['multi_source_matches'],1)
 def test_same_symbol_different_contract(self):
  self.add('cg','one');self.add('cmc','1',addr=B);self.assertEqual(self.run_sync()['unique_assets'],2)
 def test_unresolved(self):
  self.add('cg','native',None);self.add('cmc','1',None);s=self.run_sync();self.assertEqual((s['unique_assets'],s['unresolved']),(2,2))
 def test_cross_chain_not_address_alone(self):
  self.add('cg','one');self.add('cmc','1',chain='base');self.assertEqual(self.run_sync()['unique_assets'],2)
 def test_verified_cross_chain(self):
  self.add('cg','one');self.add('cmc','1',chain='base');u.schema(self.c)
  self.c.execute('INSERT INTO wm_unified_identity_links VALUES(?,?,?,?,?,?)',('cg','one','cmc','1','fixture official ID map, evidence reference',1));self.c.commit()
  s=self.run_sync();self.assertEqual((s['unique_assets'],s['chain_tokens']),(1,2))
 def test_unverified_link_ignored(self):
  self.add('cg','one');self.add('cmc','1',addr=B);u.schema(self.c)
  self.c.execute('INSERT INTO wm_unified_identity_links VALUES(?,?,?,?,?,?)',('cg','one','cmc','1','same symbol',0));self.c.commit();self.assertEqual(self.run_sync()['unique_assets'],2)
 def test_conflict_keeps_raw(self):
  self.add('cg','one',price=1);self.add('cmc','1',price=2);s=self.run_sync();self.assertEqual(s['field_conflicts'],1);self.assertEqual(self.rows()[0]['quality_status'],'CONFLICT');self.assertEqual(self.c.execute('SELECT COUNT(*) FROM wm_unified_raw_versions').fetchone()[0],2)
 def test_missing_not_zero(self):
  self.add('cmc','1',price=None,cap=None,vol=None);self.run_sync();r=self.rows()[0];self.assertIsNone(r['price_usd']);self.assertIsNone(r['volume_24h']);self.assertIsNone(r['market_cap'])
 def test_pool_not_asset_volume(self):
  self.add('dex','ethereum:'+A,vol=500,liq=20);self.run_sync();r=self.rows()[0];self.assertIsNone(r['volume_24h']);self.assertIsNone(r['market_cap']);self.assertEqual(r['liquidity_usd'],20);self.assertEqual(json.loads(r['pool_data_json'])[0]['volume_usd'],500)
 def test_different_dates_not_compared(self):
  self.add('cg','one',price=1);self.add('cmc','1',day='2026-10-09',price=2,basis='utc_finalized');s=self.run_sync();self.assertEqual(s['field_conflicts'],0);self.assertIsNone(self.c.execute("SELECT difference_ratio FROM wm_unified_conflicts WHERE field='price_usd'").fetchone()[0])
 def test_quote_time_not_collection_time(self):
  self.add('cg','one',day='2026-10-10',price=1);self.add('cmc','1',day='2026-10-09',price=2,basis='utc_finalized');self.run_sync();self.assertEqual(self.rows()[0]['price_usd'],1)
 def test_seven_days_real_and_idempotent(self):
  for i in range(4,11):self.add('cmc','1',day=f'2026-10-{i:02d}',price=i,basis='utc_finalized')
  before=[tuple(r) for r in self.c.execute('SELECT * FROM wm_market_observations')];self.run_sync();s=self.run_sync();self.assertEqual(s['recomputed_assets'],0);self.assertEqual(s['full_seven_day_assets'],1);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM wm_unified_daily').fetchone()[0],7);self.assertEqual(before,[tuple(r) for r in self.c.execute('SELECT * FROM wm_market_observations')]);self.assertAlmostEqual(self.c.execute("SELECT daily_return FROM wm_unified_daily WHERE date_utc='2026-10-10'").fetchone()[0],(10/9-1)*100)
 def test_intraday_no_fake_returns(self):
  self.add('cg','one',day='2026-10-09');self.add('cg','one',day='2026-10-10',price=2);self.assertEqual(self.run_sync()['daily_return_assets'],0)
 def test_mixed_source_no_fake_returns(self):
  self.add('cg','one',day='2026-10-09',basis='utc_finalized');self.add('cmc','1',price=2,basis='utc_finalized');self.assertEqual(self.run_sync()['daily_return_assets'],0)
 def test_missing_date_no_bridge_returns(self):
  self.add('cmc','1',day='2026-10-08',basis='utc_finalized');self.add('cmc','1',price=2,basis='utc_finalized');self.assertEqual(self.run_sync()['daily_return_assets'],0)
 def test_raw_versions_preserved(self):
  self.add('cmc','1');self.run_sync();self.add('cmc','1',price=2);self.run_sync();self.assertEqual(self.c.execute('SELECT COUNT(*) FROM wm_unified_raw_versions').fetchone()[0],2);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM wm_unified_daily').fetchone()[0],1)
 def test_incremental_only_affected(self):
  self.add('cg','one');self.add('cmc','2',addr=B);self.run_sync();self.add('cg','one',price=3);self.assertEqual(self.run_sync()['recomputed_assets'],1)
 def test_failure_rollback(self):
  self.add('cg','one');self.run_sync();before=self.rows();self.add('cg','one',price=3)
  with self.assertRaises(RuntimeError):u.sync(self.c,fail_before_commit=True)
  self.assertEqual(self.rows(),before);self.assertEqual(self.run_sync()['recomputed_assets'],1)
 def test_quality_unchanged_zero_network(self):
  self.add('cg','one');before=[tuple(r) for r in self.c.execute('SELECT * FROM wm_quality_reports')]
  with patch.object(socket,'socket',side_effect=AssertionError('network')),patch.object(ingest,'request_json',side_effect=AssertionError('API')):
   self.assertEqual(self.run_sync()['external_api_calls'],0)
  self.assertEqual(before,[tuple(r) for r in self.c.execute('SELECT * FROM wm_quality_reports')])
 def test_invalid_contract_not_merge(self):
  self.add('cg','one',addr='invalid');self.add('cmc','1',addr='invalid');self.assertEqual(self.run_sync()['unique_assets'],2)
 def test_stable_id_when_new_source(self):
  self.add('cmc','1');self.run_sync();cid=self.rows()[0]['canonical_asset_id'];self.add('cg','one');self.run_sync();self.assertEqual(self.rows()[0]['canonical_asset_id'],cid)
 def test_sol_case_sensitive(self):
  self.assertNotEqual(u.chain_token('solana','A'*32),u.chain_token('solana','a'*32))
 def test_primary_quality_before_freshness(self):
  self.add('cg','one',price=1);self.add('cmc','1',price=2,day='2026-10-09',basis='utc_finalized');self.c.execute("UPDATE wm_quality_reports SET status='blocked' WHERE provider='cg'");self.c.commit();self.run_sync();self.assertEqual(self.rows()[0]['primary_source'],'cmc')
 def test_stale_quote_cannot_fill_a_new_date(self):
  self.add('cg','one')
  self.c.execute("INSERT INTO wm_cg_snapshots(snapshot_id,date_utc,started_at_utc,time_basis,status) VALUES('cg:test','2026-10-10','2026-10-10T12:00:00+00:00','intraday','complete')")
  self.c.execute('INSERT INTO wm_cg_staged VALUES(?,?,?,?)',('cg:test','one',1,json.dumps({'last_updated':'2026-10-09T12:00:00Z'})))
  self.c.commit();self.run_sync()
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM wm_unified_daily').fetchone()[0],0)
  self.assertIsNotNone(self.rows()[0]['price_usd'])
 def test_history_missing_quality(self):
  self.add('cg','one');self.run_sync()
  self.assertIn('price_history_7d',json.loads(self.rows()[0]['missing_fields']))
  self.assertIn('daily_return',json.loads(self.rows()[0]['missing_fields']))
 def test_trusted_cross_quote_valid_without_pool_or_history(self):
  # v1.7: DEX pool liquidity and 7d history gaps are orthogonal dimensions; a trusted
  # CG/CMC cross-confirmed current quote with all core fields is VALID for decisions.
  self.add('cg','one',price=1,cap=100,vol=10);self.add('cmc','1',addr=A,price=1.01,cap=101,vol=11)
  self.c.execute("INSERT INTO wm_cg_snapshots(snapshot_id,date_utc,started_at_utc,time_basis,status) VALUES('cg:v17','2026-10-10','2026-10-10T12:00:00+00:00','intraday','complete')")
  self.c.execute('INSERT INTO wm_cg_staged VALUES(?,?,?,?)',('cg:v17','one',1,json.dumps({'market_cap_rank':7,'price_change_percentage_24h':2.5,'last_updated':'2026-10-10T12:00:00Z'})))
  self.c.commit();self.run_sync();r=self.rows()[0]
  self.assertEqual(r['quality_status'],'VALID');self.assertNotEqual(r['identity_confidence'],'UNRESOLVED')
  self.assertIn('price_history_7d',json.loads(r['missing_fields']))
  self.assertIn('liquidity_usd',json.loads(r['missing_fields']))
 def test_missing_core_field_keeps_partial(self):
  self.add('cg','one',price=None,cap=100,vol=10)
  self.c.execute("INSERT INTO wm_cg_snapshots(snapshot_id,date_utc,started_at_utc,time_basis,status) VALUES('cg:x','2026-10-10','2026-10-10T12:00:00+00:00','intraday','complete')")
  self.c.execute('INSERT INTO wm_cg_staged VALUES(?,?,?,?)',('cg:x','one',1,json.dumps({'market_cap_rank':7,'price_change_percentage_24h':2.5})))
  self.c.commit();self.run_sync();self.assertEqual(self.rows()[0]['quality_status'],'PARTIAL')
 def test_invalid_close_falls_back_to_real_intraday_without_inventing_return(self):
  self.add('cg','one',price=3);self.add('cmc','1',price=None,basis='utc_finalized')
  self.run_sync();row=self.c.execute('SELECT price_usd,time_basis,daily_return FROM wm_unified_daily').fetchone()
  self.assertEqual(tuple(row),(3,'intraday',None))
  self.assertIn('daily_return',json.loads(self.rows()[0]['missing_fields']))
 def test_incremental_dates_and_adjacent_return(self):
  for i in range(4,11):self.add('cmc','1',day=f'2026-10-{i:02d}',price=i,basis='utc_finalized')
  self.run_sync();self.add('cmc','1',day='2026-10-06',price=12,basis='utc_finalized')
  result=self.run_sync();self.assertEqual(result['recomputed_dates'],2)
  self.assertAlmostEqual(self.c.execute("SELECT daily_return FROM wm_unified_daily WHERE date_utc='2026-10-07'").fetchone()[0],(7/12-1)*100)
  self.assertEqual(self.run_sync()['recomputed_dates'],0)
 def test_empty_database_before_first_collection(self):
  result=self.run_sync();self.assertEqual(result['unique_assets'],0);self.assertIsNone(result['synced_at']);self.assertEqual(self.run_sync()['recomputed_dates'],0)
if __name__=='__main__':unittest.main()
