#!/bin/sh
# Usage: ./run_demo.sh          -> replay apnea demo on the board
#        ./run_demo.sh live     -> live from the AFE4950 EVM
#        ./run_demo.sh normal   -> replay normal case
cd "$(dirname "$0")"
pkill -f dashboard.py 2>/dev/null
IP=$(hostname -I | awk '{print $1}')
echo "Open on the presenting laptop:  http://$IP:8000"
case "$1" in
  live)   exec python3 dashboard.py live --export-dir exports ;;
  normal) exec python3 dashboard.py data/c01 120 ;;
  *)      exec python3 dashboard.py data/a01 120 ;;
esac
