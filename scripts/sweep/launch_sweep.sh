#!/usr/bin/env bash
mkdir -p $(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/results
nohup python3 $(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_coarse_sweep.py SA > $(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/results/log.sweep_SA 2>&1 &
PID_SA=$!
echo "SA sweep launched with PID $PID_SA"

nohup python3 $(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_coarse_sweep.py SST > $(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/results/log.sweep_SST 2>&1 &
PID_SST=$!
echo "SST sweep launched with PID $PID_SST"

echo "Sweep processes active. Monitor with: tail -f results/log.sweep_SA and results/log.sweep_SST"
