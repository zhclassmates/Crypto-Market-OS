import json
import sqlite3
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import history_coverage as h

class HistoryCoverageTests(unittest.TestCase):
 def setUp(self):
  self.start=1770000000//h.DAY*h.DAY;self.end=self.start+8*h.DAY
 def bar(self,day=0,close='2',**extra):
  return {'time':self.start+day*h.DAY,'close':close,**extra}
 def validate(self,raw,created=None):
  return h.validate_bar(raw,self.end,self.start,self.end,created)
 def test_exact_utc_only(self):
  self.assertIsNone(self.validate(self.bar(time=self.start+3600)))
 def test_ms_timestamp(self):
  self.assertEqual(self.validate(self.bar(time=self.start*1000))['ts'],self.start)
 def test_partial_today_rejected(self):
  self.assertIsNone(self.validate(self.bar(8)))
 def test_unfinished_bar_rejected(self):
  self.assertIsNone(h.validate_bar(self.bar(7),self.end-1,self.start,self.end))
 def test_no_timestamp(self):
  self.assertIsNone(self.validate({'close':'2'}))
 def test_invalid_price(self):
  for price in ['0','-1','NaN','Infinity',None]:self.assertIsNone(self.validate(self.bar(close=price)))
 def test_prebirth(self):
  self.assertIsNone(self.validate(self.bar(),self.start+h.DAY))
 def test_birth_day_allowed(self):
  self.assertIsNotNone(self.validate(self.bar(),self.start+500))
 def test_ohlc_bounds(self):
  self.assertIsNone(self.validate(self.bar(low='3')))
  self.assertIsNone(self.validate(self.bar(high='1')))
 def test_eight_prices_required(self):
  self.assertEqual(len(h.return_days({self.start+i*h.DAY:2 for i in range(8)},self.start,self.end)),7)
  self.assertEqual(len(h.return_days({self.start+i*h.DAY:2 for i in range(1,8)},self.start,self.end)),6)
 def test_real_zero_return(self):
  self.assertEqual(h.return_days({self.start:2,self.start+h.DAY:2},self.start,self.end),{self.start+h.DAY:0})
 def test_no_gap_splice(self):
  self.assertEqual(h.return_days({self.start:2,self.start+2*h.DAY:3},self.start,self.end),{})
 def test_short_history_participates(self):
  self.assertEqual(len(h.return_days({self.start+6*h.DAY:2,self.start+7*h.DAY:3},self.start,self.end)),1)
 def test_existing_guards_preserved(self):
  for old,new in [(1e-9,2e-9),(1,100)]:self.assertEqual(h.return_days({self.start:old,self.start+h.DAY:new},self.start,self.end),{})
 def test_missing_ranges(self):
  self.assertEqual(h.missing_ranges({self.start:2,self.start+3*h.DAY:2},self.start,self.start+5*h.DAY),[(self.start+h.DAY,self.start+3*h.DAY),(self.start+4*h.DAY,self.start+5*h.DAY)])
 def test_insert_never_overwrites(self):
  db=sqlite3.connect(':memory:');db.execute('CREATE TABLE daily_kline(chain,address,ts,open,high,low,close,volume,amount,fetched_at,finalized_at,PRIMARY KEY(chain,address,ts))')
  first=self.validate(self.bar());other={**first,'close':'99'}
  self.assertEqual(len(h.insert_missing(db,'sol','a',[first])),1)
  self.assertEqual(h.insert_missing(db,'sol','a',[other]),[])
  self.assertEqual(db.execute('SELECT close FROM daily_kline').fetchone()[0],'2')
 def test_archive_identity_and_time(self):
  db=sqlite3.connect(':memory:');db.execute('CREATE TABLE wm_unified_raw_versions(provider,provider_id,date_utc,payload_json)')
  address='0x'+'a'*40;row={'chain':'eth','address':address,'token_created_at':None}
  raw={**self.bar(),'ts':self.start,'fetched_at':self.end,'finalized_at':self.end}
  raw.pop('time')
  payload={'raw_chain':'eth','raw_address':address,'time_basis':'utc_finalized','raw_bar':raw}
  date=h.dt.datetime.fromtimestamp(self.start,h.dt.timezone.utc).date().isoformat()
  def add(p):db.execute('INSERT INTO wm_unified_raw_versions VALUES(?,?,?,?)',('gmgn','ethereum:'+address,date,json.dumps(p)))
  add({**payload,'raw_address':'wrong'});self.assertEqual(h.recover_archive(db,row,self.start,self.end,self.end),[])
  add(payload);self.assertEqual(len(h.recover_archive(db,row,self.start,self.end,self.end)),1)
 def test_future_archive_evidence(self):
  db=sqlite3.connect(':memory:');db.execute('CREATE TABLE wm_unified_raw_versions(provider,provider_id,date_utc,payload_json)')
  address='0x'+'a'*40;payload={'raw_chain':'eth','raw_address':address,'time_basis':'utc_finalized','raw_bar':{'ts':self.start,'close':'2','fetched_at':self.end+1}}
  date=h.dt.datetime.fromtimestamp(self.start,h.dt.timezone.utc).date().isoformat()
  db.execute('INSERT INTO wm_unified_raw_versions VALUES(?,?,?,?)',('gmgn','ethereum:'+address,date,json.dumps(payload)))
  self.assertEqual(h.recover_archive(db,{'chain':'eth','address':address},self.start,self.end,self.end),[])

class RecoveryCheckpointTests(unittest.TestCase):
 def test_conflicting_provider_identity_rejected(self):
  ts=1770000000//h.DAY*h.DAY
  raw={'time':ts,'close':'2','address':'different'}
  self.assertIsNone(h.validate_bar(raw,ts+8*h.DAY,ts,ts+8*h.DAY,identity=('sol','requested')))
 def fixture(self,folder):
  now=1770000000//h.DAY*h.DAY+8*h.DAY
  path=Path(folder);dbpath=path/'source.sqlite'
  db=sqlite3.connect(dbpath);db.execute('CREATE TABLE daily_kline(chain,address,ts,open,high,low,close,volume,amount,fetched_at,finalized_at,PRIMARY KEY(chain,address,ts))');db.close()
  corepath=path/'core.sqlite';sqlite3.connect(corepath).close()
  row={'chain':'sol','address':'test-address','token_created_at':None}
  report=path/'report';report.mkdir();(report/'plan.json').write_text(json.dumps({'now':now,'assets':[row],'baseline':{}}))
  def connect(_,readonly=False):
   c=sqlite3.connect(corepath if readonly else dbpath);c.row_factory=sqlite3.Row;return c
  return report,now,connect,row
 def test_uncertain_receipt_is_not_repeated(self):
  with tempfile.TemporaryDirectory() as folder:
   report,now,connect,row=self.fixture(folder);key=(row['chain'],row['address']);left=now-8*h.DAY;right=now
   ident=h.hashlib.sha256(f'{key}:{left}:{right}'.encode()).hexdigest()+'.json'
   (report/'requests.jsonl').write_text(json.dumps({'id':ident})+'\n')
   with patch.object(h,'connect',connect),patch.object(h,'recover_archive',return_value=[]),patch.object(h.subprocess,'run') as run:
    result=h.sample(report,100,100,True,5)
   run.assert_not_called();self.assertEqual(result['api_requests'],1);self.assertEqual(result['inserted_bars'],0)
 def test_saved_response_recovers_without_request(self):
  with tempfile.TemporaryDirectory() as folder:
   report,now,connect,row=self.fixture(folder);key=(row['chain'],row['address']);left=now-8*h.DAY;right=now
   ident=h.hashlib.sha256(f'{key}:{left}:{right}'.encode()).hexdigest()+'.json'
   (report/'requests.jsonl').write_text(json.dumps({'id':ident})+'\n')
   (report/ident).write_text(json.dumps({'response':{'list':[{'time':left+i*h.DAY,'close':'2'} for i in range(8)]},'fetched_at':now}))
   with patch.object(h,'connect',connect),patch.object(h,'recover_archive',return_value=[]),patch.object(h.subprocess,'run') as run,patch.object(h.time,'sleep'):
    result=h.sample(report,100,100,True,5)
    again=h.sample(report,100,100,True,5)
   run.assert_not_called();self.assertEqual(result['inserted_bars'],8);self.assertEqual(result['new_full_assets'],1);self.assertEqual(again['inserted_bars'],8);self.assertEqual(again['api_requests'],1)

class ManifestAndLockTests(unittest.TestCase):
 def fixture(self):
  db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;db.execute('CREATE TABLE token_registry(chain,address,token_created_at,first_seen_at)')
  address='0x'+'a'*40;db.execute('INSERT INTO token_registry VALUES(?,?,?,?)',('eth',address,123,100));return db,address
 def test_manifest_uses_registry_identity_and_birth(self):
  db,address=self.fixture()
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'assets.json';path.write_text(json.dumps([{'chain':'eth','address':address,'token_created_at':999},{'chain':'eth','address':address}]))
   rows=h.manifest_candidates(db,path,100)
   self.assertEqual(len(rows),1);self.assertEqual(rows[0]['token_created_at'],123)
 def test_manifest_requires_already_registered_asset(self):
  db,address=self.fixture()
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'assets.json';path.write_text(json.dumps([{'chain':'eth','address':'0x'+'b'*40}]))
   with self.assertRaisesRegex(ValueError,'absent'):h.manifest_candidates(db,path,100)
 def test_parallel_checkpoint_process_is_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)
   with (path/'run.lock').open('a') as lock:
    h.fcntl.flock(lock,h.fcntl.LOCK_EX|h.fcntl.LOCK_NB)
    with self.assertRaisesRegex(RuntimeError,'already running'):h.sample(path,100,100,True)

if __name__=='__main__':unittest.main()
