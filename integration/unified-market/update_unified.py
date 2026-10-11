import json,sqlite3,hashlib,shutil
from pathlib import Path
stage=Path(__file__).parent;target=Path(json.loads((stage/'install-manifest.json').read_text())['target'])
c=sqlite3.connect(target/'data/world_model_market.sqlite',timeout=30)
tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'wm_unified_%' ORDER BY name")]
def hashes():return {t:hashlib.sha256(repr([tuple(r) for r in c.execute('SELECT * FROM '+t+' ORDER BY 1,2')]).encode()).hexdigest() for t in tables}
before=hashes()
for src,dest in [('unified_market.py','unified_market.py'),('unified_onchain.py','unified_onchain.py'),('test_unified_market.py','tests/test_unified_market.py'),('README.md','UNIFIED_MARKET.md')]:shutil.copy2(stage/src,target/dest)
import sys
sys.path.insert(0,str(target));import unified_market
first=unified_market.sync(c);second=unified_market.sync(c);assert before==hashes();assert second['recomputed_assets']==0
out={'first':first,'second':second,'original_tables_unchanged':True}
(stage/'final-db-verification.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2));c.close()
