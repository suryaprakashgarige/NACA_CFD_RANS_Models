#!/usr/bin/env python3
import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
import sys
import json
import time
import subprocess
import threading

SCRIPTS_ROOT = os.path.join(PROJECT_ROOT, "scripts", "sweep")
CASES_ROOT = os.path.join(PROJECT_ROOT, "cases")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")

def run_case_worker(af, model, alpha, fallback, results_dict, key):
    cmd = ["python3", os.path.join(SCRIPTS_ROOT, "run_single_fresh.py"), af, model, str(alpha)]
    if fallback:
        cmd.append("--fallback")
    print(f"[RUNNER] Launching: {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True)
    
    # Read result.json
    res_path = os.path.join(CASES_ROOT, af, model, f"a{alpha:02d}", "result.json")
    with open(res_path) as f:
        res = json.load(f)
    results_dict[key] = res

def update_sst_results(new_results):
    res_file = os.path.join(RESULTS_DIR, "sweep_results_SST.json")
    with open(res_file) as f:
        all_res = json.load(f)
        
    for new_r in new_results:
        # replace or append
        replaced = False
        for i, existing in enumerate(all_res):
            if existing["airfoil"] == new_r["airfoil"] and int(existing["alpha"]) == int(new_r["alpha"]):
                all_res[i] = new_r
                replaced = True
                break
        if not replaced:
            all_res.append(new_r)
            
    with open(res_file, "w") as f:
        json.dump(all_res, f, indent=2)
    print(f"[RUNNER] Updated {res_file} successfully.", flush=True)

def main():
    print("==================================================================", flush=True)
    print("STARTING AUTONOMOUS FRESH RE-RUN PIPELINE FOR DIVERGED SST CASES", flush=True)
    print("==================================================================", flush=True)
    
    # Wave 1: 4412 a04 and a08
    print("\n>>> WAVE 1: naca4412/SST a04 & a08 (Concurrent, 3 ranks each) <<<", flush=True)
    wave1_results = {}
    t1 = threading.Thread(target=run_case_worker, args=("naca4412", "SST", 4, False, wave1_results, "4412_a04"))
    t2 = threading.Thread(target=run_case_worker, args=("naca4412", "SST", 8, False, wave1_results, "4412_a08"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    
    # Plausibility check on 4412
    a04 = wave1_results["4412_a04"]
    a08 = wave1_results["4412_a08"]
    print(f"\n[PLAUSIBILITY CHECK] 4412 a04: Cl={a04['cl']:.4f} (target 0.88-0.92), Cd={a04['cd']:.5f} (target 0.009-0.011)")
    print(f"[PLAUSIBILITY CHECK] 4412 a08: Cl={a08['cl']:.4f} (target 1.28-1.33)")
    
    # Check if retry needed
    retry_needed = []
    if not (0.80 <= a04["cl"] <= 1.00 and 0.007 <= a04["cd"] <= 0.015):
        print("WARNING: 4412 a04 outside expected plausible range. Retrying with fallback relaxation (p 0.2 / U 0.5)!", flush=True)
        retry_needed.append(("naca4412", "SST", 4))
    if not (1.20 <= a08["cl"] <= 1.40):
        print("WARNING: 4412 a08 outside expected plausible range. Retrying with fallback relaxation (p 0.2 / U 0.5)!", flush=True)
        retry_needed.append(("naca4412", "SST", 8))
        
    for af, model, alpha in retry_needed:
        key = f"{af[-4:]}_a{alpha:02d}"
        run_case_worker(af, model, alpha, True, wave1_results, key)
        
    update_sst_results(list(wave1_results.values()))
    
    # Wave 2: 4412 a12 and a15
    print("\n>>> WAVE 2: naca4412/SST a12 & a15 (Concurrent, 3 ranks each) <<<", flush=True)
    wave2_results = {}
    t1 = threading.Thread(target=run_case_worker, args=("naca4412", "SST", 12, False, wave2_results, "4412_a12"))
    t2 = threading.Thread(target=run_case_worker, args=("naca4412", "SST", 15, False, wave2_results, "4412_a15"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    update_sst_results(list(wave2_results.values()))
    
    # Wave 3: 2412 a04 and a08
    print("\n>>> WAVE 3: naca2412/SST a04 & a08 (Concurrent, 3 ranks each) <<<", flush=True)
    wave3_results = {}
    t1 = threading.Thread(target=run_case_worker, args=("naca2412", "SST", 4, False, wave3_results, "2412_a04"))
    t2 = threading.Thread(target=run_case_worker, args=("naca2412", "SST", 8, False, wave3_results, "2412_a08"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    update_sst_results(list(wave3_results.values()))
    
    # Wave 4: 2412 a12 and a15
    print("\n>>> WAVE 4: naca2412/SST a12 & a15 (Concurrent, 3 ranks each) <<<", flush=True)
    wave4_results = {}
    t1 = threading.Thread(target=run_case_worker, args=("naca2412", "SST", 12, False, wave4_results, "2412_a12"))
    t2 = threading.Thread(target=run_case_worker, args=("naca2412", "SST", 15, False, wave4_results, "2412_a15"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    update_sst_results(list(wave4_results.values()))
    
    print("\n==================================================================", flush=True)
    print("ALL FRESH RE-RUNS COMPLETED! PROCEEDING TO FINAL COMPILATION", flush=True)
    print("==================================================================", flush=True)

if __name__ == "__main__":
    main()
