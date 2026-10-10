#!/bin/sh
# Revive contract; also supports this existing local checkout.
if [ -d /workspace ]; then
  cd /workspace || exit 1
else
  cd "$(dirname "$0")" || exit 1
fi
if curl -fsS -o /dev/null --max-time 3 http://127.0.0.1:8080/; then
  exit 0
fi
# Detached process group + closed stdin survive the tool shell returning.
# A lock and PID prevent duplicate starts while Vite is warming up.
python3 - <<'PY'
import fcntl,os,subprocess,time,urllib.request
from pathlib import Path
root=Path.cwd();state=root/'.grok';state.mkdir(exist_ok=True)
with (state/'dev-start.lock').open('w') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 pidfile=state/'dev-server.pid'
 if pidfile.exists():
  try:
   os.kill(int(pidfile.read_text()),0)
   raise SystemExit(0)
  except (ValueError,ProcessLookupError):pass
 with (state/'dev.log').open('ab') as log:
  child=subprocess.Popen(['npm','run','dev'],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
 pidfile.write_text(str(child.pid))
# Wait for server to be ready (max 30s)
for _ in range(60):
  try:
   urllib.request.urlopen('http://127.0.0.1:8080/', timeout=2)
   break
  except:
   time.sleep(0.5)
PY
