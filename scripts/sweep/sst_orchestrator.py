#!/usr/bin/env python3
import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
import re
import subprocess
import time
import json
import numpy as np
import shutil
import threading
import queue

CASES_ROOT = os.path.join(PROJECT_ROOT, "cases")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
SCRIPTS_ROOT = os.path.join(PROJECT_ROOT, "scripts", "sweep")
RANKS = 3
CHECK_INTERVAL = 10

# Remaining 6 SST Jobs
sst_jobs = [
    # NACA 2412
    ("naca2412", "SST", 15, "naca2412/SST/a12"),
    
    # NACA 4412 Chain
    ("naca4412", "SST", 0, None),
    ("naca4412", "SST", 4, "naca4412/SST/a00"),
    ("naca4412", "SST", 8, "naca4412/SST/a04"),
    ("naca4412", "SST", 12, "naca4412/SST/a08"),
    ("naca4412", "SST", 15, "naca4412/SST/a12"),
]

def get_force_data(case_dir):
    fc_dir = os.path.join(case_dir, "postProcessing", "forceCoeffs")
    if not os.path.exists(fc_dir):
        return None
    subdirs = sorted(os.listdir(fc_dir))
    if not subdirs:
        return None
    dat_file = os.path.join(fc_dir, subdirs[-1], "forceCoeffs.dat")
    if not os.path.exists(dat_file):
        return None
    data = []
    with open(dat_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 4:
                try:
                    t = float(parts[0])
                    cm = float(parts[1])
                    cd = float(parts[2])
                    cl = float(parts[3])
                    data.append([t, cm, cd, cl])
                except ValueError:
                    continue
    if not data:
        return None
    return np.array(data)

def parse_yplus(case_dir):
    log_file = os.path.join(case_dir, "log.yPlus")
    if not os.path.exists(log_file):
        return 0.0
    yplus_max = 0.0
    with open(log_file) as f:
        for line in f:
            if "patch airfoil y+" in line:
                m = re.search(r"max\s*=\s*([0-9.eE+-]+)", line)
                if m:
                    yplus_max = float(m.group(1))
    return yplus_max

def count_bounding_k(case_dir):
    log_file = os.path.join(case_dir, "log.foamRun")
    if not os.path.exists(log_file):
        return 0
    count = 0
    with open(log_file, errors='ignore') as f:
        for line in f:
            if "bounding k" in line:
                count += 1
    return count

def get_relax_factor(case_dir):
    fvs = os.path.join(case_dir, "system", "fvSolution")
    if not os.path.exists(fvs):
        return "0.7"
    with open(fvs) as f:
        text = f.read()
    m = re.search(r'"\(nuTilda\|k\|omega\)"\s+([0-9.]+);', text)
    if m:
        return m.group(1)
    return "0.7"

results_lock = threading.RLock()
jobs_lock = threading.RLock()
results_file = os.path.join(RESULTS_DIR, "sweep_results_SST.json")

# Load existing completed results
with open(results_file, "r") as f:
    completed_results = json.load(f)

def save_results():
    with results_lock:
        with open(results_file, "w") as f:
            json.dump(completed_results, f, indent=2)

def run_job(job, worker_id):
    af, model, alpha, parent = job
    case_dir = os.path.join(CASES_ROOT, af, model, f"a{alpha:02d}")
    print(f"\n[Worker-{worker_id}] Starting {af}/{model}/a{alpha:02d} (parent: {parent})", flush=True)
    start_time = time.time()
    
    # 1. Clean old processor/time dirs if any
    if os.path.exists(case_dir):
        for item in os.listdir(case_dir):
            path = os.path.join(case_dir, item)
            if item.startswith("processor") and os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.isdir(path) and item not in ["0", "constant", "system"]:
                try:
                    t = float(item)
                    if t > 0:
                        shutil.rmtree(path)
                except ValueError:
                    pass
        pp = os.path.join(case_dir, "postProcessing")
        if os.path.exists(pp):
            shutil.rmtree(pp)

    # 2. Setup case
    parent_dir = os.path.join(CASES_ROOT, parent) if parent else ""
    setup_cmd = f"python3 {SCRIPTS_ROOT}/setup_sweep_case.py {af} {model} {float(alpha)}"
    if parent_dir:
        setup_cmd += f" {parent_dir}"
    subprocess.run(["bash", "-c", setup_cmd], check=True)

    # Modify controlDict for cap and automated 500-step writes
    cd_path = os.path.join(case_dir, "system", "controlDict")
    with open(cd_path) as f:
        cd_text = f.read()
    cap = 3000 if alpha >= 12 else 2500
    cd_text = re.sub(r"endTime\s+\d+;", f"endTime         {cap};", cd_text)
    cd_text = re.sub(r"stopAt\s+\w+;", "stopAt          endTime;", cd_text)
    cd_text = re.sub(r"writeInterval\s+\d+;", "writeInterval   500;", cd_text, count=1)
    cd_text = re.sub(r"purgeWrite\s+\d+;", "purgeWrite      1;", cd_text)
    with open(cd_path, "w") as f:
        f.write(cd_text)

    # Decompose
    subprocess.run(["bash", "-c", f"source /opt/openfoam13/etc/bashrc && cd {case_dir} && decomposePar > log.decomposePar 2>&1"], check=True)

    # Run
    cmd_run = (
        f"source /opt/openfoam13/etc/bashrc && cd {case_dir} && "
        f"mpirun --mca btl_vader_single_copy_mechanism none -np {RANKS} foamRun -parallel > log.foamRun 2>&1"
    )
    proc = subprocess.Popen(["bash", "-c", cmd_run])
    
    plateau_met = False
    is_stall = (alpha >= 12)
    
    while proc.poll() is None:
        time.sleep(CHECK_INTERVAL)
        data = get_force_data(case_dir)
        if data is None or len(data) < 200:
            continue
            
        cur_iter = int(data[-1, 0])
        
        # Check plateau for non-stall
        if not is_stall and len(data) >= 500:
            cd_500 = data[-500:, 2]
            cl_500 = data[-500:, 3]
            mean_cd = max(abs(np.mean(cd_500)), 1e-4)
            mean_cl = np.mean(cl_500)
            
            d_cd_pct = (np.max(cd_500) - np.min(cd_500)) / mean_cd * 100
            d_cl_pct = (np.max(cl_500) - np.min(cl_500)) / max(abs(mean_cl), 1e-4) * 100
            cl_cond = (d_cl_pct < 0.2) or (np.max(cl_500) - np.min(cl_500) < 0.002)
            cd_cond = (d_cd_pct < 0.5)

            if cd_cond and cl_cond:
                print(f"[Worker-{worker_id}] Plateau met for {af}/{model}/a{alpha:02d} at iter {cur_iter}! Stopping with writeNow.", flush=True)
                with open(cd_path) as f:
                    ct = f.read()
                ct = ct.replace("stopAt          endTime;", "stopAt          writeNow;")
                with open(cd_path, "w") as f:
                    f.write(ct)
                plateau_met = True
                break
                
        # Near cap: trigger writeNow so the final time step is written cleanly
        if cur_iter >= cap - 5:
            print(f"[Worker-{worker_id}] Reached cap ({cur_iter}/{cap}) for {af}/{model}/a{alpha:02d}. Stopping with writeNow.", flush=True)
            with open(cd_path) as f:
                ct = f.read()
            ct = ct.replace("stopAt          endTime;", "stopAt          writeNow;")
            with open(cd_path, "w") as f:
                f.write(ct)
            break
            
    proc.wait()
    wall_time = time.time() - start_time
    
    # Reconstruct
    subprocess.run(["bash", "-c", f"source /opt/openfoam13/etc/bashrc && cd {case_dir} && reconstructPar -latestTime > log.reconstructPar 2>&1"], check=False)
    
    # Run yPlus with -solver incompressibleFluid
    subprocess.run(["bash", "-c", f"source /opt/openfoam13/etc/bashrc && cd {case_dir} && foamPostProcess -solver incompressibleFluid -func yPlus -latestTime > log.yPlus 2>&1"], check=False)
    
    data = get_force_data(case_dir)
    res = {
        "case": case_dir, "airfoil": af, "model": model, "alpha": float(alpha),
        "wall_time": wall_time, "iterations": 0, "cl": 0.0, "cd": 0.0, "cm": 0.0,
        "yplus_max": parse_yplus(case_dir), "flag": "",
        "bounding_k": count_bounding_k(case_dir),
        "relax_factor": get_relax_factor(case_dir)
    }
    
    if data is not None and len(data) > 0:
        res["iterations"] = int(data[-1, 0])
        if is_stall and len(data) >= 800:
            last800 = data[-800:]
            res["cm"] = float(np.mean(last800[:, 1]))
            res["cd"] = float(np.mean(last800[:, 2]))
            res["cl"] = float(np.mean(last800[:, 3]))
            res["flag"] = "cap_800avg"
            if (np.max(last800[:, 2]) - np.min(last800[:, 2])) / max(abs(res["cd"]), 1e-4) * 100 > 2.0:
                res["flag"] += "_unsteady"
        else:
            res["cm"] = float(data[-1, 1])
            res["cd"] = float(data[-1, 2])
            res["cl"] = float(data[-1, 3])
            res["flag"] = "plateau" if plateau_met else "cap_hit"
            
    print(f"[Worker-{worker_id}] FINISHED {af}/{model}/a{alpha:02d}: Cl={res['cl']:.5f} Cd={res['cd']:.5f} y+={res['yplus_max']:.3f} k_bnd={res['bounding_k']} flag={res['flag']}", flush=True)
    return res

remaining_jobs = list(sst_jobs)

def worker(worker_id):
    while True:
        target_job = None
        with jobs_lock:
            if not remaining_jobs:
                break
            # Find a job whose parent is finished
            for i, job in enumerate(remaining_jobs):
                af, model, alpha, parent = job
                if parent is None:
                    target_job = remaining_jobs.pop(i)
                    break
                else:
                    with results_lock:
                        parent_done = any(r["case"].endswith(parent) for r in completed_results)
                    if parent_done:
                        target_job = remaining_jobs.pop(i)
                        break
        
        if target_job is None:
            time.sleep(5)
            continue
            
        res = run_job(target_job, worker_id)
        with results_lock:
            completed_results.append(res)
        save_results()

# Start 2 worker threads (2 lanes * 3 ranks = 6 ranks)
t1 = threading.Thread(target=worker, args=(1,))
t2 = threading.Thread(target=worker, args=(2,))
t1.start()
t2.start()

t1.join()
t2.join()

print("\n=== ALL SST SWEEP RUNS FINISHED ===", flush=True)
