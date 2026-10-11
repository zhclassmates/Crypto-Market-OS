"""Resume the existing V1.7 projection upgrade; never recollect or reinstall."""
import datetime as dt
import hashlib
import json
import shutil
import socket
import sqlite3
import sys
import time
from pathlib import Path

stage = Path(__file__).resolve().parent
workspace = stage.parents[1]
core = Path(json.loads((stage / 'install-manifest.json').read_text())['target'])
checkpoint = workspace / 'backups/resume-20261011'
sys.path.insert(0, str(core))
import unified_market as unified

# Network use is forbidden for this local projection upgrade.
def no_network(*args, **kwargs):
    raise AssertionError('Resume sync must not call the network')
socket.create_connection = no_network
socket.socket.connect = no_network
socket.socket.connect_ex = no_network

c = sqlite3.connect(core / 'data/world_model_market.sqlite', timeout=120)
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'wm_unified_%' AND name!='sqlite_sequence' ORDER BY name")]
def raw_hashes():
    result = {}
    for table in tables:
        digest = hashlib.sha256()
        quoted = '"' + table.replace('"', '""') + '"'
        for row in c.execute('SELECT * FROM ' + quoted + ' ORDER BY 1,2'):
            digest.update(repr(tuple(row)).encode())
        result[table] = digest.hexdigest()
    return result

before = raw_hashes()
old_ids = {r[0] for r in c.execute('SELECT canonical_asset_id FROM wm_unified_current')}
version = c.execute("SELECT value FROM wm_unified_meta WHERE key='version'").fetchone()[0]
previous = checkpoint / 'v17-before.json'
saved = json.loads(previous.read_text()) if previous.exists() else {}
if saved.get('version') == version and saved.get('raw_hashes') == before and Path(saved['backup']).joinpath('world_model_market.sqlite').exists():
    backup = Path(saved['backup'])
else:
    backup = checkpoint / ('before-v17-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir()
    with sqlite3.connect(backup / 'world_model_market.sqlite') as target:
        c.backup(target)
    for file in ('unified_market.py', 'unified_onchain.py', 'market_ingest.py'):
        shutil.copy2(core / file, backup / file)
(checkpoint / 'v17-before.json').write_text(json.dumps({'version':version,'backup':str(backup),'raw_hashes':before,'old_asset_count':len(old_ids)}, indent=2))
print('Recoverable database/code checkpoint ready; existing version ' + version, flush=True)
# The live collector keeps changing. Freeze only its three input tables in a
# read-only transaction so the repeated sync checks identical observations.
onchain_path = Path(c.execute("SELECT value FROM wm_unified_meta WHERE key='onchain_db'").fetchone()[0])
frozen = backup / 'onchain-input-snapshot.sqlite'
with sqlite3.connect(onchain_path.resolve().as_uri() + '?mode=ro', uri=True) as source:
    source.execute('PRAGMA query_only=ON')
    source.execute('BEGIN')
    with sqlite3.connect(frozen) as output:
        for table in ('tokens', 'token_snapshot', 'daily_kline'):
            output.execute(source.execute('SELECT sql FROM sqlite_master WHERE name=?', (table,)).fetchone()[0])
            count = len(source.execute('PRAGMA table_info(' + table + ')').fetchall())
            output.executemany('INSERT INTO ' + table + ' VALUES(' + ','.join('?' for _ in range(count)) + ')', source.execute('SELECT * FROM ' + table))
    source.rollback()
print('Consistent read-only onchain input snapshot saved', flush=True)
started = time.monotonic()
first = unified.sync(c, rh_db=str(frozen))
print('V1.7 sync published: ' + json.dumps(first), flush=True)
assert before == raw_hashes(), 'Original ingestion tables changed'
new_ids = {r[0] for r in c.execute('SELECT canonical_asset_id FROM wm_unified_current')}
redirects = dict(c.execute('SELECT old_id,canonical_asset_id FROM wm_unified_redirects'))
for identity in old_ids - new_ids:
    seen = set()
    while identity in redirects and identity not in seen:
        seen.add(identity)
        identity = redirects[identity]
    assert identity in new_ids, 'Existing asset identity lost'
second = unified.sync(c, rh_db=str(frozen))
assert second['recomputed_assets'] == second['recomputed_dates'] == 0, 'No-op sync not incremental'
assert before == raw_hashes(), 'Original ingestion tables changed on repeat sync'
# Restore the existing live source for subsequent collector-triggered updates.
unified.upsert(c, 'wm_unified_meta', {'key':'onchain_db','value':str(onchain_path.resolve())}, ['key'])
c.commit()
result = {'version':unified.VERSION,'backup':str(backup),'first':first,'second':second,
          'raw_unchanged':True,'raw_hashes':before,'existing_identities_preserved':True,
          'onchain_input_snapshot':str(frozen),'live_onchain_path_restored':str(onchain_path.resolve()),
          'quality':dict(c.execute('SELECT quality_status,COUNT(*) FROM wm_unified_current GROUP BY quality_status')),
          'native_assets':[list(r) for r in c.execute("SELECT name,quality_status,missing_fields FROM wm_unified_current WHERE identity_confidence='VERIFIED_MAPPING'")],
          'elapsed_seconds':round(time.monotonic()-started,3)}
(checkpoint / 'v17-verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2),flush=True)
c.close()
