#!/usr/bin/env bash
# B1: memory and responsiveness with K concurrent headless Claude Code sessions (uses a little usage).
# Usage (from the repository root): benchmarks/infra/cc_concurrency.sh 3
set -euo pipefail
K="${1:-3}"; LOG="$(mktemp -d)"
for i in $(seq 1 "$K"); do
  claude -p "Read every file under tools/mfos/mfos and list, for each, its three most important functions. Be thorough." \
    --output-format json --max-turns 25 --max-budget-usd 0.50 --permission-mode dontAsk \
    --allowedTools "Read,Grep,Glob" > "$LOG/s$i.json" 2>&1 &
done
peak=0
while pgrep -f "claude -p" > /dev/null; do
  mb=$(ps -axo rss=,command= | grep "[c]laude" | awk '{s+=$1} END {print int(s/1024)}')
  [ "${mb:-0}" -gt "$peak" ] && peak=$mb
  sleep 1
done
wait || true
echo "sessions=$K  peak total RSS of claude processes: ${peak} MB"
command -v memory_pressure > /dev/null && memory_pressure | tail -1
