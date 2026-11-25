#!/usr/bin/env python3
import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
import sys
import time
import subprocess
import json

RUNNER = os.path.join(PROJECT_ROOT, "scripts", "sweep", "run_case_plateau.py")
CASES = os.path.join(PROJECT_ROOT, "cases", "naca0012_L1")

def run_pair(case1, case2=None):
    procs = []
    c1_name = f"{os.path.basename(os.path.dirname(case1))}/{os.path.basename(case1)}"
    print(f"\n========================================================")
    print(f"LAUNCHING CONCURRENT RUNS:")
    print(f"  [1] {c1_name}")
    p1 = subprocess.Popen(["python3", RUNNER, case1])
    procs.append((c1_name, p1))
    
    if case2:
        c2_name = f"{os.path.basename(os.path.dirname(case2))}/{os.path.basename(case2)}"
        print(f"  [2] {c2_name}")
        p2 = subprocess.Popen(["python3", RUNNER, case2])
        procs.append((c2_name, p2))
    print(f"========================================================\n")
    
    for name, p in procs:
        p.wait()
        print(f"Process {name} completed.")

def main():
    start_total = time.time()
    
    # Run SST a00 and SA a10 concurrently
    c_sst_a00 = os.path.join(CASES, "SST", "a00")
    c_sa_a10 = os.path.join(CASES, "SA", "a10")
    run_pair(c_sst_a00, c_sa_a10)
    
    # Run SST a10
    c_sst_a10 = os.path.join(CASES, "SST", "a10")
    # run_pair(c_sst_a10)
    
    total_wall = time.time() - start_total
    print(f"\nAll verification runs completed in {total_wall:.1f} s ({total_wall/60:.2f} min).")

if __name__ == "__main__":
    main()
