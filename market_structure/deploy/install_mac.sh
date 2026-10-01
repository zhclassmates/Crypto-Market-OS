#!/usr/bin/env bash
# 在 Mac 上安装并常驻运行采集器（launchd，开机/登录自启，崩溃自动拉起）。
# 用法：在 market_structure/ 目录下执行
#   bash deploy/install_mac.sh              # 默认用 python3
#   bash deploy/install_mac.sh /path/to/python3.11
#   bash deploy/install_mac.sh --uninstall
set -euo pipefail

cd "$(dirname "$0")/.."
DIR="$(pwd)"
LABEL="com.cryptoos.market-structure"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "已卸载常驻任务（数据保留在 $DIR/data）"
  exit 0
fi

PY="${1:-python3}"
"$PY" -c 'import sys; assert sys.version_info >= (3, 9), "需要 Python 3.9+"'

echo "==> 建虚拟环境并安装依赖"
[[ -d .venv ]] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

if [[ ! -f config.toml ]]; then
  cp config.example.toml config.toml
  echo "==> 已生成 config.toml（默认只有 BTCUSDT / ETHUSDT，把十月实验候选币加进去）"
fi

if [[ -n "${HTTPS_PROXY:-${https_proxy:-}}" ]] && grep -qE '^proxy = ""' config.toml; then
  echo "!! 注意：你的终端设置了代理 ${HTTPS_PROXY:-${https_proxy:-}}，但 launchd 常驻进程不会继承终端环境变量。"
  echo "!! 如果访问交易所需要代理，请把它写进 config.toml 的 proxy = \"...\"，然后重新运行本脚本。"
fi

echo "==> 先跑一轮 REST 回补（首次约几分钟：30 天 K 线 / OI / 资金费率）"
.venv/bin/python -m ms once --config config.toml

mkdir -p logs "$HOME/Library/LaunchAgents"
# caffeinate -i：采集器运行期间阻止 Mac 空闲睡眠（合盖仍会睡；睡眠期间强平会断档，REST 数据醒来后自动补齐）
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string><string>-i</string>
    <string>$DIR/.venv/bin/python</string><string>-m</string><string>ms</string>
    <string>run</string><string>--config</string><string>$DIR/config.toml</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$DIR/logs/launchd.out</string>
  <key>StandardErrorPath</key><string>$DIR/logs/launchd.err</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "==> 已常驻运行。查看状态：launchctl print gui/$(id -u)/$LABEL | grep state"
echo "==> 健康检查：cd \"$DIR\" && .venv/bin/python -m ms health"
echo "==> 日志：$DIR/logs/collector.log；每晚报告：$DIR/reports/"
