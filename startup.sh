#!/bin/sh
# Grok sandbox 下项目固定在 /workspace；本机 checkout 时使用脚本所在目录
if [ -d /workspace ]; then
  cd /workspace || exit 1
  LOG=/tmp/rh-dev.log
else
  cd "$(dirname "$0")" || exit 1
  LOG="$PWD/.grok/preview.log"
fi

if curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:8080/; then
  exit 0
fi

nohup npm run dev > "$LOG" 2>&1 &
