#!/usr/bin/env python3
"""Refresh the existing local projection, never fetch remote data.

One locked worker per checkout. Failed sync rolls back and retries on the next
interval; the last published market remains readable throughout.
"""
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]

def refresh(core, source, sync_fn=None):
    if sync_fn is None:
        sys.path.insert(0, str(core))
        import unified_market
        sync_fn = unified_market.sync
    db = sqlite3.connect(core / 'data/world_model_market.sqlite', timeout=30)
    try:
        with db: return sync_fn(db, rh_db=str(source))
    finally: db.close()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--loop', action='store_true')
    parser.add_argument('--interval', type=int, default=300)
    args = parser.parse_args()
    manifest = ROOT / 'integration/unified-market/install-manifest.json'
    if not manifest.exists(): return 0
    core = Path(json.loads(manifest.read_text())['target'])
    source = Path(os.environ.get('RH_MARKET_DB', str(ROOT / 'rh_v2/market.sqlite')))
    if not (core / 'data/world_model_market.sqlite').exists() or not source.exists(): return 0
    state = ROOT / '.grok'
    state.mkdir(exist_ok=True)
    with (state / 'unified-refresh.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return 0
        # This worker cannot spend API quota or expose credentials to a request.
        def offline(*a, **kw): raise RuntimeError('Projection refresh is local-only')
        socket.create_connection = offline
        socket.socket.connect = offline
        socket.socket.connect_ex = offline
        while True:
            status = {'attempted_at': dt.datetime.now(dt.timezone.utc).isoformat()}
            print(json.dumps({**status, 'running': True}), flush=True)
            try:
                status.update(ok=True, result=refresh(core, source))
                try:
                    sys.path.insert(0,str(ROOT/'integration/unified-market'))
                    import history_monitor
                    status['coverage']=history_monitor.publish(core,source,state,int(time.time()))
                except Exception as error:
                    status['coverage_error']=type(error).__name__+': '+str(error)
            except Exception as error:
                status.update(ok=False, error=type(error).__name__ + ': ' + str(error))
            temp = state / 'unified-refresh-status.tmp'
            temp.write_text(json.dumps(status, indent=2))
            temp.replace(state / 'unified-refresh-status.json')
            print(json.dumps(status), flush=True)
            if not args.loop: return 0 if status['ok'] else 1
            time.sleep(max(60, args.interval))

if __name__ == '__main__': raise SystemExit(main())
