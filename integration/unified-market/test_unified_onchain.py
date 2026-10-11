import datetime as dt,json,sqlite3,tempfile,unittest
from pathlib import Path
from test_unified_market import UnifiedTests,A,B
import unified_market as u
import unified_onchain as adapter
class OnchainTests(UnifiedTests):
 # Reuse setup, not inherited test methods (removed below) to avoid double reporting.
 def setUp(self):
  super().setUp();self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'source.sqlite';r=sqlite3.connect(self.path)
  r.executescript('''CREATE TABLE tokens(chain TEXT,address TEXT,symbol TEXT,name TEXT,first_seen_at INTEGER,token_created_at INTEGER,PRIMARY KEY(chain,address));
  CREATE TABLE token_snapshot(chain TEXT,address TEXT,ts INTEGER,price TEXT,volume_24h TEXT,liquidity TEXT,market_cap TEXT,pc_24h TEXT,
    price_source TEXT,price_updated_at INTEGER,volume_24h_source TEXT,volume_24h_updated_at INTEGER,liquidity_source TEXT,liquidity_updated_at INTEGER,market_cap_source TEXT,market_cap_updated_at INTEGER,pc_24h_source TEXT,pc_24h_updated_at INTEGER,price_ds TEXT,volume_ds TEXT,liquidity_ds TEXT,PRIMARY KEY(chain,address));
  CREATE TABLE daily_kline(chain TEXT,address TEXT,ts INTEGER,open TEXT,high TEXT,low TEXT,close TEXT,volume TEXT,amount TEXT,fetched_at INTEGER,finalized_at INTEGER,PRIMARY KEY(chain,address,ts));''')
  r.close()
 def stamp(self,day,hour=0):return int(dt.datetime.fromisoformat(day+f'T{hour:02d}:00:00+00:00').timestamp())
 def token(self,address=A,chain='eth',created=None):
  with sqlite3.connect(self.path) as r:
   r.execute('INSERT OR IGNORE INTO tokens VALUES(?,?,?,?,?,?)',(chain,address,'SAME','Same',self.stamp('2026-10-08'),self.stamp(created) if created else None))
 def bar(self,day,price,address=A,chain='eth',observed='2026-10-10',hour=12):
  self.token(address,chain)
  with sqlite3.connect(self.path) as r:r.execute('INSERT OR REPLACE INTO daily_kline VALUES(?,?,?,?,?,?,?,?,?,?,?)',(chain,address,self.stamp(day),str(price),str(price),str(price),str(price),'10',None,self.stamp(observed,hour),None))
 def snap(self,address=A,ds=None):
  self.token(address)
  t=self.stamp('2026-10-10',12)
  with sqlite3.connect(self.path) as r:r.execute('INSERT OR REPLACE INTO token_snapshot VALUES('+','.join('?' for _ in range(21))+')',('eth',address,t,'3','1000','500','10000','0.125','hot',t,'hot',t,'hot',t,'hot',t,'hot',t,ds,ds,ds))
 def run_sync(self):return u.sync(self.c,rh_db=str(self.path))
 def test_gmgn_contract_join_existing_canonical(self):
  self.add('cg','one');u.sync(self.c);id=self.rows()[0]['canonical_asset_id'];self.snap();r=self.run_sync()
  self.assertEqual(r['unique_assets'],1);self.assertEqual(self.rows()[0]['canonical_asset_id'],id);self.assertEqual(self.rows()[0]['source_count'],2)
 def test_finalized_real_returns_and_partial_newcoin(self):
  self.bar('2026-10-08',2);self.bar('2026-10-09',3);self.run_sync()
  row=self.c.execute("SELECT daily_return,return_quality FROM wm_unified_daily WHERE date_utc='2026-10-09'").fetchone();self.assertEqual(tuple(row),(50,'VALID'))
  self.assertEqual(len(self.rows()),1);self.assertEqual(self.rows()[0]['quality_status'],'PARTIAL')
 def test_open_bar_not_finalized(self):
  self.bar('2026-10-10',3);self.run_sync();self.assertEqual(self.c.execute('SELECT COUNT(*) FROM wm_unified_daily').fetchone()[0],0)
 def test_preclose_fetch_never_becomes_final_by_calendar(self):
  self.bar('2026-10-08',2,observed='2026-10-08');self.run_sync();self.assertEqual(self.c.execute('SELECT COUNT(*) FROM wm_unified_daily').fetchone()[0],0)
 def test_source_gap_no_return(self):
  self.bar('2026-10-07',2);self.bar('2026-10-09',3);self.assertEqual(self.run_sync()['daily_return_assets'],0)
 def test_pair_uses_same_source_even_with_cmc_day(self):
  self.add('cmc','1',day='2026-10-08',price=100,basis='utc_finalized');self.bar('2026-10-08',2);self.bar('2026-10-09',3);self.run_sync()
  self.assertEqual(self.c.execute("SELECT daily_return FROM wm_unified_daily WHERE date_utc='2026-10-09'").fetchone()[0],50)
 def test_low_base_and_extreme_excluded(self):
  self.bar('2026-10-08',1e-10);self.bar('2026-10-09',1e-8);self.run_sync();self.assertEqual(self.c.execute("SELECT return_quality FROM wm_unified_daily WHERE date_utc='2026-10-09'").fetchone()[0],'LOW_BASE_PRICE');self.assertEqual(self.c.execute("SELECT daily_return FROM wm_unified_daily WHERE date_utc='2026-10-09'").fetchone()[0],None)
 def test_missing_dex_timestamp_does_not_override(self):
  self.snap(ds='999');self.run_sync();r=self.rows()[0];self.assertEqual(r['price_usd'],3);self.assertEqual(r['volume_24h'],1000);self.assertEqual(r['liquidity_usd'],500);self.assertTrue(json.loads(r['pool_data_json'])[0]['timestamp_missing'])
 def test_gmgn_percent_and_scope_not_summed(self):
  self.add('cg','one',vol=10,cap=100);self.snap();self.run_sync();r=self.rows()[0];self.assertEqual(r['volume_24h'],10);self.assertEqual(r['market_cap'],100);self.assertEqual(r['price_change_24h'],12.5)
  # A field adopted from local-only gmgn observations is not blanket-trusted: not decision VALID.
  self.assertNotEqual(r['quality_status'],'VALID')
 def test_different_chain_does_not_merge(self):
  self.add('cg','one');self.token(A,chain='base');self.assertEqual(self.run_sync()['unique_assets'],2)
 def test_read_only_and_idempotent(self):
  self.snap();before=self.path.read_bytes();self.run_sync();self.assertEqual(self.run_sync()['recomputed_assets'],0);self.assertEqual(self.path.read_bytes(),before)
 def test_creation_eligibility(self):
  self.assertFalse(adapter.final_bar({'ts':self.stamp('2026-10-07'),'fetched_at':self.stamp('2026-10-10'),'finalized_at':None},self.stamp('2026-10-08'),self.stamp('2026-10-10',12)))
 def test_native_id_link_does_not_merge_wrapped_contract(self):
  self.add('cg','solana',addr=None,chain=None);self.add('cmc','5426',addr=None,chain=None);self.add('cg','wrapped-solana',addr='So11111111111111111111111111111111111111112',chain='solana');u.schema(self.c)
  self.c.execute('INSERT INTO wm_unified_identity_links VALUES(?,?,?,?,?,1)',('cg','solana','cmc','5426',json.dumps({'kind':'verified_native_ids','native_chain':'solana','references':['official CG and CMC pages']})));self.c.commit();r=self.run_sync();self.assertEqual(r['unique_assets'],2)
  self.assertTrue(any(json.loads(row['chains'])==['solana'] and row['identity_confidence']=='VERIFIED_MAPPING' for row in self.rows()))
 def test_existing_tier_thresholds_and_main_history(self):
  self.snap()
  with sqlite3.connect(self.path) as r:
   r.execute('CREATE TABLE token_registry(chain TEXT,address TEXT,first_liquidity_50k_at INTEGER,kline_backfilled_at INTEGER)')
   r.execute('INSERT INTO token_registry VALUES(?,?,?,?)',('eth',A,1,None))
  self.run_sync();self.assertEqual(self.rows()[0]['market_tier'],'MAIN')
  for liquidity,expected in [('19999','OBSERVE'),('20000','EARLY'),('49999','EARLY'),('50000','MAIN')]:
   with sqlite3.connect(self.path) as r:
    r.execute('DELETE FROM token_registry');r.execute('UPDATE token_snapshot SET liquidity=?',(liquidity,))
   self.run_sync();self.assertEqual(self.rows()[0]['market_tier'],expected)
 def test_registry_only_asset_still_visible_without_quotes(self):
  with sqlite3.connect(self.path) as r:
   r.execute('CREATE TABLE token_registry(chain TEXT,address TEXT,symbol TEXT,name TEXT,first_seen_at INTEGER)')
   r.execute('INSERT INTO token_registry VALUES(?,?,?,?,?)',('eth',A,'NEW','New',self.stamp('2026-10-10')))
  self.assertEqual(self.run_sync()['unique_assets'],1)
  row=self.rows()[0];self.assertEqual(row['market_tier'],'UNKNOWN');self.assertIsNone(row['price_usd'])
  self.assertEqual(self.run_sync()['recomputed_assets'],0)
 def test_missing_source_database_preserves_published_other_sources(self):
  self.add('cg','one');self.snap();self.run_sync()
  before=[dict(r) for r in self.c.execute('SELECT * FROM wm_unified_current')]
  with self.assertRaises(sqlite3.OperationalError):u.sync(self.c,rh_db=str(self.path.parent/'missing.sqlite'))
  self.assertEqual([dict(r) for r in self.c.execute('SELECT * FROM wm_unified_current')],before)
# Keep the original 28 tests in UnifiedTests once; this adapter class owns only its additions.
OnchainTests.__bases__=(unittest.TestCase,)
OnchainTests.add=UnifiedTests.add;OnchainTests.rows=UnifiedTests.rows
# Use setup directly, because super() follows the adjusted base.
_original_setup=OnchainTests.setUp
# replace super setup invocation with an explicit base fixture setup
import inspect
# No dynamic source execution needed: fixture setup duplicated via wrapper temporarily.
def setup(self):
 UnifiedTests.setUp(self)
 self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'source.sqlite'
 r=sqlite3.connect(self.path)
 r.executescript('''CREATE TABLE tokens(chain TEXT,address TEXT,symbol TEXT,name TEXT,first_seen_at INTEGER,token_created_at INTEGER,PRIMARY KEY(chain,address));
 CREATE TABLE token_snapshot(chain TEXT,address TEXT,ts INTEGER,price TEXT,volume_24h TEXT,liquidity TEXT,market_cap TEXT,pc_24h TEXT,price_source TEXT,price_updated_at INTEGER,volume_24h_source TEXT,volume_24h_updated_at INTEGER,liquidity_source TEXT,liquidity_updated_at INTEGER,market_cap_source TEXT,market_cap_updated_at INTEGER,pc_24h_source TEXT,pc_24h_updated_at INTEGER,price_ds TEXT,volume_ds TEXT,liquidity_ds TEXT,PRIMARY KEY(chain,address));
 CREATE TABLE daily_kline(chain TEXT,address TEXT,ts INTEGER,open TEXT,high TEXT,low TEXT,close TEXT,volume TEXT,amount TEXT,fetched_at INTEGER,finalized_at INTEGER,PRIMARY KEY(chain,address,ts));''');r.close()
OnchainTests.setUp=setup
if __name__=='__main__':unittest.main()
