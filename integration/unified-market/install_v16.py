"""One-time verified upgrade in the EXISTING DB; frozen read-only inputs for audit."""
import datetime as dt,hashlib,json,shutil,sqlite3,sys,time
from pathlib import Path
stage=Path(__file__).parent;target=Path(json.loads((stage/'install-manifest.json').read_text())['target']);workspace=stage.parents[1]
rh=workspace/'rh_v2/market.sqlite';frozen=Path('/private/tmp/wm-onchain-rank-proof.sqlite')
start=time.monotonic();source=sqlite3.connect(rh.resolve().as_uri()+'?mode=ro',uri=True);source.execute('PRAGMA query_only=ON');source.execute('BEGIN')
proof=sqlite3.connect(frozen);proof.execute('PRAGMA journal_mode=WAL')
for table in ('tokens','token_snapshot','daily_kline'):
 proof.execute('DROP TABLE IF EXISTS '+table)
 proof.execute(source.execute('SELECT sql FROM sqlite_master WHERE name=?',(table,)).fetchone()[0])
 fields=len(source.execute('PRAGMA table_info('+table+')').fetchall())
 proof.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in range(fields))+')',source.execute('SELECT * FROM '+table))
proof.commit();source.rollback();source.close();proof.close()
print('Read-only onchain freeze complete',flush=True)
for src,dest in [('unified_market.py','unified_market.py'),('unified_onchain.py','unified_onchain.py'),('test_unified_market.py','tests/test_unified_market.py'),('README.md','UNIFIED_MARKET.md')]:shutil.copy2(stage/src,target/dest)
sys.path.insert(0,str(target));import unified_market as u
c=sqlite3.connect(target/'data/world_model_market.sqlite',timeout=60)
raw_tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'wm_unified_%' ORDER BY name")]
def hashes():
 out={}
 for table in raw_tables:
  h=hashlib.sha256()
  for row in c.execute('SELECT * FROM '+table+' ORDER BY 1,2'):h.update(repr(tuple(row)).encode())
  out[table]=h.hexdigest()
 return out
before=hashes();old_ids={r[0] for r in c.execute('SELECT canonical_asset_id FROM wm_unified_current')}
backup=target/'data'/('unified-rank-backup-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir()
out=sqlite3.connect(backup/'world_model_market.sqlite');c.backup(out);out.close()
for filename in ('unified_market.py','unified_onchain.py','market_ingest.py'):
 if (target/filename).exists():shutil.copy2(target/filename,backup/filename)
u.schema(c)
for cg,cmc,chain in [('bitcoin','1','bitcoin'),('ethereum','1027','ethereum'),('solana','5426','solana')]:
 rows=c.execute('SELECT address FROM wm_market_assets WHERE asset_key IN (?,?)',('cg:'+cg,'cmc:'+cmc)).fetchall()
 assert len(rows)==2 and all(not r[0] for r in rows),'Native link must not include wrapped/bridged contracts'
 evidence={'kind':'verified_native_ids','native_chain':chain,'cg_id':cg,'cmc_id':cmc,'checked_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
 'references':['https://www.coingecko.com/en/coins/'+cg,'https://coinmarketcap.com/currencies/'+cg+'/'],
 'basis':'Official provider asset pages + existing official-ID raw aliases; both raw assets have no contract. Never matches symbol/name or wrapped tokens.'}
 c.execute('INSERT OR IGNORE INTO wm_unified_identity_links VALUES(?,?,?,?,?,1)',('cg',cg,'cmc',cmc,u.js(evidence)))
c.commit()
first=u.sync(c,rh_db=str(frozen));print('First sync complete',json.dumps(first),flush=True)
second=u.sync(c,rh_db=str(frozen));assert second['recomputed_assets']==second['recomputed_dates']==0
assert before==hashes(),'Original DB changed'
# Freeze is an audit fixture, NOT a second live market database. Daily ingestion reads the existing source.
u.upsert(c,'wm_unified_meta',{'key':'onchain_db','value':str(rh.resolve())},['key']);c.commit()
new_ids={r[0] for r in c.execute('SELECT canonical_asset_id FROM wm_unified_current')}
redirects=dict(c.execute('SELECT old_id,canonical_asset_id FROM wm_unified_redirects'))
assert all(cid in new_ids or cid in redirects for cid in old_ids),'Existing canonical identity lost'
result={'first':first,'second':second,'raw_unchanged':True,'original_hashes':before,'backup':str(backup),
 'original_assets':len(old_ids),'preserved_existing_ids':len(old_ids&new_ids),'redirected_existing_ids':len(old_ids-new_ids),
 'onchain_original_opened_read_only':True,'frozen_fixture':str(frozen),'elapsed_seconds':round(time.monotonic()-start,3)}
(stage/'rank-db-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));c.close()
