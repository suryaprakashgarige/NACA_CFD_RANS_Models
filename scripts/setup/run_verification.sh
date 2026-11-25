#!/bin/bash

ALLRUN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/Allrun"
CASES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/cases/naca0012_L1"

echo "=========================================================="
echo "STARTING NACA 0012 MEDIUM GRID (L1) VERIFICATION RUNS"
echo "Layout: 2 concurrent cases x 3 MPI ranks (6 cores total)"
echo "=========================================================="

run_pair() {
    CASE1="$1"
    CASE2="$2"
    echo "--- Running pair: $(basename $(dirname $CASE1))/$(basename $CASE1) AND $(basename $(dirname $CASE2))/$(basename $CASE2) ---"
    
    $ALLRUN "$CASE1" > "$CASE1/run.stdout" 2>&1 &
    PID1=$!
    
    $ALLRUN "$CASE2" > "$CASE2/run.stdout" 2>&1 &
    PID2=$!
    
    wait $PID1
    echo "Finished: $(basename $(dirname $CASE1))/$(basename $CASE1)"
    cat "$CASE1/run.stdout" | grep -E "SUMMARY|yPlus"
    
    wait $PID2
    echo "Finished: $(basename $(dirname $CASE2))/$(basename $CASE2)"
    cat "$CASE2/run.stdout" | grep -E "SUMMARY|yPlus"
}

# Pair 1: alpha = 0 (SA and SST)
run_pair "$CASES_DIR/SA/a00" "$CASES_DIR/SST/a00"

# Pair 2: alpha = 10 (SA and SST)
run_pair "$CASES_DIR/SA/a10" "$CASES_DIR/SST/a10"

# Pair 3: alpha = 15 (SA and SST)
run_pair "$CASES_DIR/SA/a15" "$CASES_DIR/SST/a15"

echo "=========================================================="
echo "ALL 6 VERIFICATION RUNS COMPLETED"
echo "=========================================================="
