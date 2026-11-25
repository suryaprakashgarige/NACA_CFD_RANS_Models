#!/usr/bin/env python3
import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
import subprocess
import json

SCRIPTS_ROOT = os.path.join(PROJECT_ROOT, "scripts", "sweep")
CASES_ROOT = os.path.join(PROJECT_ROOT, "cases")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")

def main():
    print("[RERUN] Launching fresh naca2412/SST/a04 with standard relaxation...", flush=True)
    cmd = ["python3", os.path.join(SCRIPTS_ROOT, "run_single_fresh.py"), "naca2412", "SST", "4"]
    subprocess.run(cmd, check=True)
    
    res_path = os.path.join(CASES_ROOT, "naca2412", "SST", "a04", "result.json")
    with open(res_path) as f:
        res = json.load(f)
    print(f"[RERUN RESULT] 2412 a04: Cl={res['cl']:.5f}, Cd={res['cd']:.5f}, Cm={res['cm']:.5f}, y+={res['yplus_max']:.3f}, flag={res['flag']}", flush=True)

    # Update sweep_results_SST.json
    sst_file = os.path.join(RESULTS_DIR, "sweep_results_SST.json")
    all_res = []
    if os.path.exists(sst_file):
        with open(sst_file) as f:
            all_res = json.load(f)
    replaced = False
    for i, r in enumerate(all_res):
        if r["airfoil"] == "naca2412" and int(r["alpha"]) == 4:
            all_res[i] = res
            replaced = True
            break
    if not replaced:
        all_res.append(res)
    with open(sst_file, "w") as f:
        json.dump(all_res, f, indent=2)
    print(f"[RERUN] Updated {sst_file} with fresh 2412 a04.", flush=True)

if __name__ == "__main__":
    main()
