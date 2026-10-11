"""Concrete reviewed deployment. Requires external-directory filesystem permission."""
import datetime,hashlib,json,shutil,sqlite3,sys
from pathlib import Path
stage=Path(__file__).parent
m=json.loads((stage/'install-manifest.json').read_text());target=Path(m['target']);ingest=target/'market_ingest.py'
original=ingest.read_bytes()
assert hashlib.sha256(original).hexdigest()==m['ingest_sha256'],'Collector changed since review; do not overwrite'
text=original.decode()
needle='    con.close()\n    return 1 if failures else 0'
assert text.count(needle)==1
hook='''    try:
        # Unified V1: additive local-only projection after the existing quality gate.
        # Failure cannot change collection status or published source health.
        import unified_market
        print("UNIFIED " + json.dumps(unified_market.sync(con), ensure_ascii=False))
    except Exception as exc:
        print(f"Unified market error (last good view retained): {exc}", file=sys.stderr)
    con.close()
    return 1 if failures else 0'''
path=target/'data/world_model_market.sqlite'
c=sqlite3.connect(path,timeout=30)
tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'wm_%' AND name NOT LIKE 'wm_unified_%' ORDER BY name")]
def hashes():return {t:hashlib.sha256(repr([tuple(r) for r in c.execute('SELECT * FROM '+t+' ORDER BY 1,2')]).encode()).hexdigest() for t in tables}
before=hashes()
backup=target/'data'/('unified-backup-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir()
b=sqlite3.connect(backup/path.name);c.backup(b);b.close()
(backup/'market_ingest.py').write_bytes(original)
for src,dest in [('unified_market.py','unified_market.py'),('test_unified_market.py','tests/test_unified_market.py'),('README.md','UNIFIED_MARKET.md')]:shutil.copy2(stage/src,target/dest)
ingest.write_text(text.replace(needle,hook))
sys.path.insert(0,str(target))
import unified_market
try:
 result=unified_market.sync(c)
 assert before==hashes(),'Original rows changed'
 second=unified_market.sync(c)
 assert second['recomputed_assets']==0
 out={'first':result,'second':second,'original_tables_unchanged':True,'backup':str(backup)}
 (stage/'installed-verification.json').write_text(json.dumps(out,indent=2))
 print(json.dumps(out,indent=2))
except BaseException:
 ingest.write_bytes(original)
 raise
finally:c.close()
