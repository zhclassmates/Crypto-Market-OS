import hashlib,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import unified_market as u
source=sys.argv[1];dest=sys.argv[2]
src=sqlite3.connect('file:'+source+'?mode=ro',uri=True)
tables=[r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'wm_%' AND name NOT LIKE 'wm_unified_%' ORDER BY name")]
def hashes(c):
 return {t:hashlib.sha256(repr([tuple(r) for r in c.execute('SELECT * FROM '+t+' ORDER BY 1,2')]).encode()).hexdigest() for t in tables}
before=hashes(src)
out=sqlite3.connect(dest);src.backup(out);src.close()
first=u.sync(out);after=hashes(out);second=u.sync(out)
assert before==after==hashes(out),'Original data changed'
assert second['recomputed_assets']==0,'Not idempotent'
try:u.sync(out,True,True)
except RuntimeError:pass
assert hashes(out)==before
assert u.stats(out)=={k:v for k,v in first.items() if k not in ('recomputed_assets','recomputed_dates','external_api_calls')}
print(json.dumps({'first':first,'second':second,'original_hashes':before,'raw_unchanged':True,'rollback_verified':True},indent=2))
out.close()
