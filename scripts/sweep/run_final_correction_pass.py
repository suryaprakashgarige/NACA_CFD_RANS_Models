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
    print(f"\n[RUNNER] Launching: {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True)
    
    res_path = os.path.join(CASES_ROOT, af, model, f"a{alpha:02d}", "result.json")
    with open(res_path) as f:
        res = json.load(f)
    results_dict[key] = res

def update_sst_results(new_results):
    res_file = os.path.join(RESULTS_DIR, "sweep_results_SST.json")
    all_res = []
    if os.path.exists(res_file):
        with open(res_file) as f:
            all_res = json.load(f)
        
    for new_r in new_results:
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

def check_gate(res, gate_spec):
    cl = res["cl"]
    cd = res["cd"]
    passed = True
    reasons = []
    
    if "cl_min" in gate_spec and cl < gate_spec["cl_min"]:
        passed = False
        reasons.append(f"Cl={cl:.4f} < {gate_spec['cl_min']}")
    if "cl_max" in gate_spec and cl > gate_spec["cl_max"]:
        passed = False
        reasons.append(f"Cl={cl:.4f} > {gate_spec['cl_max']}")
    if "cd_min" in gate_spec and cd < gate_spec["cd_min"]:
        passed = False
        reasons.append(f"Cd={cd:.5f} < {gate_spec['cd_min']}")
    if "cd_max" in gate_spec and cd > gate_spec["cd_max"]:
        passed = False
        reasons.append(f"Cd={cd:.5f} > {gate_spec['cd_max']}")
    if cd < 0:
        passed = False
        reasons.append(f"Cd={cd:.5f} < 0 (negative drag)")
        
    return passed, ", ".join(reasons) if reasons else "PASSED"

def main():
    print("==================================================================", flush=True)
    print("STARTING FINAL CORRECTION PASS FOR 5 FRESH SST RUNS", flush=True)
    print("==================================================================", flush=True)
    
    failed_runs = []
    passed_runs = []
    
    # -------------------------------------------------------------
    # WAVE 1: naca2412/SST/a04 and a08
    # -------------------------------------------------------------
    print("\n>>> WAVE 1: naca2412/SST a04 & a08 (Concurrent, 3 ranks each) <<<", flush=True)
    w1_res = {}
    t1 = threading.Thread(target=run_case_worker, args=("naca2412", "SST", 4, False, w1_res, "2412_a04"))
    t2 = threading.Thread(target=run_case_worker, args=("naca2412", "SST", 8, False, w1_res, "2412_a08"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    
    # Gate 2412 a04: Cl 0.64–0.70, Cd 0.008–0.012
    gate_2412_a04 = {"cl_min": 0.64, "cl_max": 0.70, "cd_min": 0.008, "cd_max": 0.012}
    p, msg = check_gate(w1_res["2412_a04"], gate_2412_a04)
    print(f"[GATE] 2412 a04: {msg} (Values: Cl={w1_res['2412_a04']['cl']:.4f}, Cd={w1_res['2412_a04']['cd']:.5f})", flush=True)
    if not p:
        print("[RETRY] Retrying 2412 a04 with reduced relaxation (p 0.2 / U 0.5)...", flush=True)
        run_case_worker("naca2412", "SST", 4, True, w1_res, "2412_a04")
        p, msg = check_gate(w1_res["2412_a04"], gate_2412_a04)
        print(f"[GATE RETRY] 2412 a04: {msg}", flush=True)
        if not p:
            w1_res["2412_a04"]["flag"] = "FAILED_diverged"
            failed_runs.append(w1_res["2412_a04"])
            
    # Gate 2412 a08: Cl 1.05–1.15, Cd 0.010–0.015
    gate_2412_a08 = {"cl_min": 1.05, "cl_max": 1.15, "cd_min": 0.010, "cd_max": 0.015}
    p, msg = check_gate(w1_res["2412_a08"], gate_2412_a08)
    print(f"[GATE] 2412 a08: {msg} (Values: Cl={w1_res['2412_a08']['cl']:.4f}, Cd={w1_res['2412_a08']['cd']:.5f})", flush=True)
    if not p:
        print("[RETRY] Retrying 2412 a08 with reduced relaxation (p 0.2 / U 0.5)...", flush=True)
        run_case_worker("naca2412", "SST", 8, True, w1_res, "2412_a08")
        p, msg = check_gate(w1_res["2412_a08"], gate_2412_a08)
        print(f"[GATE RETRY] 2412 a08: {msg}", flush=True)
        if not p:
            w1_res["2412_a08"]["flag"] = "FAILED_diverged"
            failed_runs.append(w1_res["2412_a08"])
            
    update_sst_results(list(w1_res.values()))
    
    # -------------------------------------------------------------
    # WAVE 2: naca2412/SST/a12 and naca0012/SST/a15
    # -------------------------------------------------------------
    print("\n>>> WAVE 2: naca2412/SST a12 & naca0012/SST a15 (Concurrent, 3 ranks each) <<<", flush=True)
    w2_res = {}
    t1 = threading.Thread(target=run_case_worker, args=("naca2412", "SST", 12, False, w2_res, "2412_a12"))
    t2 = threading.Thread(target=run_case_worker, args=("naca0012", "SST", 15, False, w2_res, "0012_a15"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    
    # Gate 2412 a12: Cl 1.42–1.58, Cd 0.014–0.022
    gate_2412_a12 = {"cl_min": 1.42, "cl_max": 1.58, "cd_min": 0.014, "cd_max": 0.022}
    p, msg = check_gate(w2_res["2412_a12"], gate_2412_a12)
    print(f"[GATE] 2412 a12: {msg} (Values: Cl={w2_res['2412_a12']['cl']:.4f}, Cd={w2_res['2412_a12']['cd']:.5f})", flush=True)
    if not p:
        print("[RETRY] Retrying 2412 a12 with reduced relaxation (p 0.2 / U 0.5)...", flush=True)
        run_case_worker("naca2412", "SST", 12, True, w2_res, "2412_a12")
        p, msg = check_gate(w2_res["2412_a12"], gate_2412_a12)
        print(f"[GATE RETRY] 2412 a12: {msg}", flush=True)
        if not p:
            w2_res["2412_a12"]["flag"] = "FAILED_diverged"
            failed_runs.append(w2_res["2412_a12"])
            
    # Gate 0012 a15: Cl 1.4–1.8 (unsteady, 800-avg)
    gate_0012_a15 = {"cl_min": 1.40, "cl_max": 1.80, "cd_min": 0.020, "cd_max": 0.250}
    p, msg = check_gate(w2_res["0012_a15"], gate_0012_a15)
    print(f"[GATE] 0012 a15: {msg} (Values: Cl={w2_res['0012_a15']['cl']:.4f}, Cd={w2_res['0012_a15']['cd']:.5f})", flush=True)
    if not p:
        print("[RETRY] Retrying 0012 a15 with reduced relaxation (p 0.2 / U 0.5)...", flush=True)
        run_case_worker("naca0012", "SST", 15, True, w2_res, "0012_a15")
        p, msg = check_gate(w2_res["0012_a15"], gate_0012_a15)
        print(f"[GATE RETRY] 0012 a15: {msg}", flush=True)
        if not p:
            w2_res["0012_a15"]["flag"] = "FAILED_diverged"
            failed_runs.append(w2_res["0012_a15"])
            
    update_sst_results(list(w2_res.values()))
    
    # -------------------------------------------------------------
    # WAVE 3: naca4412/SST/a12 with reduced relaxation (p 0.2, U 0.5)
    # -------------------------------------------------------------
    print("\n>>> WAVE 3: naca4412/SST a12 (Fresh, p 0.2 / U 0.5) <<<", flush=True)
    w3_res = {}
    run_case_worker("naca4412", "SST", 12, True, w3_res, "4412_a12")
    
    # Gate 4412 a12: Cl 1.55–1.75, Cd 0.016–0.030
    gate_4412_a12 = {"cl_min": 1.55, "cl_max": 1.75, "cd_min": 0.016, "cd_max": 0.030}
    p, msg = check_gate(w3_res["4412_a12"], gate_4412_a12)
    print(f"[GATE] 4412 a12: {msg} (Values: Cl={w3_res['4412_a12']['cl']:.4f}, Cd={w3_res['4412_a12']['cd']:.5f})", flush=True)
    if not p:
        print("[FAIL] naca4412/SST/a12 produced nonphysical/outside gate values. Marking FAILED_diverged.", flush=True)
        w3_res["4412_a12"]["flag"] = "FAILED_diverged"
        failed_runs.append(w3_res["4412_a12"])
    else:
        passed_runs.append(w3_res["4412_a12"])
        
    update_sst_results(list(w3_res.values()))
    
    print("\n==================================================================", flush=True)
    print("ALL 5 FRESH RUNS COMPLETED. PROCEEDING TO FINAL COMPILATION", flush=True)
    print("==================================================================", flush=True)

if __name__ == "__main__":
    main()
