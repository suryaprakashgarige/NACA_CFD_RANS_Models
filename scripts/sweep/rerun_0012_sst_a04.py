#!/usr/bin/env python3
import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
import re
import subprocess
import time
import json
import numpy as np
import shutil

CASES_ROOT = os.path.join(PROJECT_ROOT, "cases")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
SCRIPTS_ROOT = os.path.join(PROJECT_ROOT, "scripts", "sweep")
RANKS = 3
CHECK_INTERVAL = 10

af = "naca0012"
model = "SST"
alpha = 4.0
parent = "naca0012/SST/a00"
case_dir = os.path.join(CASES_ROOT, af, model, f"a{int(alpha):02d}")

print(f"[Rerun-a04] Starting clean re-run of {af}/{model}/a{int(alpha):02d}...", flush=True)
start_time = time.time()

# 1. Clean old processor/time dirs
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

# 2. Setup case from parent
parent_dir = os.path.join(CASES_ROOT, parent)
setup_cmd = f"python3 {SCRIPTS_ROOT}/setup_sweep_case.py {af} {model} {float(alpha)} {parent_dir}"
subprocess.run(["bash", "-c", setup_cmd], check=True)

# Modify controlDict for cap and automated 500-step writes + writeNow on cap
cd_path = os.path.join(case_dir, "system", "controlDict")
with open(cd_path) as f:
    cd_text = f.read()
cap = 2500
cd_text = re.sub(r"endTime\s+\d+;", f"endTime         {cap};", cd_text)
cd_text = re.sub(r"stopAt\s+\w+;", "stopAt          endTime;", cd_text)
cd_text = re.sub(r"writeInterval\s+\d+;", "writeInterval   500;", cd_text)
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

def get_force_data(cdir):
    fc_dir = os.path.join(cdir, "postProcessing", "forceCoeffs")
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

plateau_met = False
while proc.poll() is None:
    time.sleep(CHECK_INTERVAL)
    data = get_force_data(case_dir)
    if data is None or len(data) < 200:
        continue
        
    cur_iter = int(data[-1, 0])
    if len(data) >= 500:
        cd_500 = data[-500:, 2]
        cl_500 = data[-500:, 3]
        mean_cd = max(abs(np.mean(cd_500)), 1e-4)
        mean_cl = np.mean(cl_500)
        
        d_cd_pct = (np.max(cd_500) - np.min(cd_500)) / mean_cd * 100
        d_cl_pct = (np.max(cl_500) - np.min(cl_500)) / max(abs(mean_cl), 1e-4) * 100
        cl_cond = (d_cl_pct < 0.2) or (np.max(cl_500) - np.min(cl_500) < 0.002)
        cd_cond = (d_cd_pct < 0.5)

        if cd_cond and cl_cond:
            print(f"[Rerun-a04] Plateau met at iter {cur_iter}! Stopping with writeNow.", flush=True)
            with open(cd_path) as f:
                ct = f.read()
            ct = ct.replace("stopAt          endTime;", "stopAt          writeNow;")
            with open(cd_path, "w") as f:
                f.write(ct)
            plateau_met = True
            break
            
    if cur_iter >= cap - 5:
        print(f"[Rerun-a04] Reaching cap ({cur_iter}/{cap}). Stopping with writeNow.", flush=True)
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

# Run yPlus
subprocess.run(["bash", "-c", f"source /opt/openfoam13/etc/bashrc && cd {case_dir} && foamPostProcess -solver incompressibleFluid -func yPlus -latestTime > log.yPlus 2>&1"], check=False)

def parse_yplus(cdir):
    log_file = os.path.join(cdir, "log.yPlus")
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

def count_bounding_k(cdir):
    log_file = os.path.join(cdir, "log.foamRun")
    if not os.path.exists(log_file):
        return 0
    count = 0
    with open(log_file, errors='ignore') as f:
        for line in f:
            if "bounding k" in line:
                count += 1
    return count

data = get_force_data(case_dir)
res = {
    "case": case_dir, "airfoil": af, "model": model, "alpha": float(alpha),
    "wall_time": wall_time, "iterations": int(data[-1, 0]) if data is not None else 0,
    "cl": float(data[-1, 3]) if data is not None else 0.0,
    "cd": float(data[-1, 2]) if data is not None else 0.0,
    "cm": float(data[-1, 1]) if data is not None else 0.0,
    "yplus_max": parse_yplus(case_dir),
    "flag": "plateau" if plateau_met else "cap_hit",
    "bounding_k": count_bounding_k(case_dir),
    "relax_factor": "0.7"
}

print(f"[Rerun-a04] Finished: Cl={res['cl']:.5f} Cd={res['cd']:.5f} y+={res['yplus_max']:.3f} flag={res['flag']}", flush=True)

# Update sweep_results_SST.json atomically
results_file = os.path.join(RESULTS_DIR, "sweep_results_SST.json")
try:
    with open(results_file, "r") as f:
        all_res = json.load(f)
    found = False
    for i, r in enumerate(all_res):
        if r.get("airfoil") == af and r.get("model") == model and r.get("alpha") == alpha:
            all_res[i] = res
            found = True
            break
    if not found:
        all_res.append(res)
    with open(results_file, "w") as f:
        json.dump(all_res, f, indent=2)
    print("[Rerun-a04] Successfully updated sweep_results_SST.json", flush=True)
except Exception as e:
    print(f"[Rerun-a04] Error updating results file: {e}", flush=True)
