#!/usr/bin/env python3
import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
import re
import subprocess
import time
import json
import shutil
import threading
import numpy as np

CASES_ROOT = os.path.join(PROJECT_ROOT, "cases")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
SCRIPTS_ROOT = os.path.join(PROJECT_ROOT, "scripts", "sweep")
RANKS = 3
CHECK_INTERVAL = 10

def backup_if_needed(case_dir):
    orig_dir = case_dir + "_orig"
    if os.path.exists(case_dir) and not os.path.exists(orig_dir):
        print(f"Backing up {case_dir} -> {orig_dir}", flush=True)
        shutil.copytree(case_dir, orig_dir)

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
    yp_file = os.path.join(case_dir, "log.yPlus")
    if not os.path.exists(yp_file):
        return 0.0
    yplus_max = 0.0
    with open(yp_file) as f:
        for line in f:
            if "airfoil" in line and ("min" in line or "max" in line):
                m = re.search(r"max\s*[:=]\s*([0-9.]+)", line)
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

def run_single_fresh_case(af, model, alpha, relax_fallback=False):
    case_dir = os.path.join(CASES_ROOT, af, model, f"a{alpha:02d}")
    print(f"\n=======================================================", flush=True)
    print(f"Starting FRESH run: {af}/{model}/a{alpha:02d} (relax_fallback={relax_fallback})", flush=True)
    print(f"=======================================================", flush=True)
    
    backup_if_needed(case_dir)
    
    # Clean old case directory completely for pristine fresh start
    if os.path.exists(case_dir):
        shutil.rmtree(case_dir)
        
    start_time = time.time()
    
    # 1. Setup case with setup_sweep_case.py (NO parent passed -> completely fresh)
    setup_cmd = f"python3 {SCRIPTS_ROOT}/setup_sweep_case.py {af} {model} {float(alpha)}"
    subprocess.run(["bash", "-c", setup_cmd], check=True)
    
    # 2. Modify controlDict: cap, writeInterval 500 (purgeWrite 1), forceCoeffs writeInterval 1
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
        
    # 3. If fallback relaxation requested (p 0.2, U 0.5)
    if relax_fallback:
        fvs_path = os.path.join(case_dir, "system", "fvSolution")
        with open(fvs_path) as f:
            fvs = f.read()
        fvs = re.sub(r"p\s+[0-9.]+;", "p               0.2;", fvs)
        fvs = re.sub(r"U\s+[0-9.]+;", "U               0.5;", fvs)
        with open(fvs_path, "w") as f:
            f.write(fvs)
            
    # 4. Decompose
    subprocess.run(["bash", "-c", f"source /opt/openfoam13/etc/bashrc && cd {case_dir} && decomposePar > log.decomposePar 2>&1"], check=True)
    
    # 5. Run solver
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
        
        # Plateau monitor for attached cases (a04, a08)
        if not is_stall and len(data) >= 500:
            cd_500 = data[-500:, 2]
            cl_500 = data[-500:, 3]
            mean_cd = max(abs(np.mean(cd_500)), 1e-4)
            mean_cl = max(abs(np.mean(cl_500)), 1e-4)
            
            d_cd_pct = (np.max(cd_500) - np.min(cd_500)) / mean_cd * 100
            d_cl_pct = (np.max(cl_500) - np.min(cl_500)) / mean_cl * 100
            cl_cond = (d_cl_pct < 0.2) or (np.max(cl_500) - np.min(cl_500) < 0.002)
            cd_cond = (d_cd_pct < 0.5)

            if cd_cond and cl_cond:
                print(f"Plateau met for {af}/{model}/a{alpha:02d} at iter {cur_iter}! Triggering writeNow.", flush=True)
                with open(cd_path) as f:
                    ct = f.read()
                ct = ct.replace("stopAt          endTime;", "stopAt          writeNow;")
                with open(cd_path, "w") as f:
                    f.write(ct)
                plateau_met = True
                break
                
        if cur_iter >= cap - 5:
            print(f"Reached cap ({cur_iter}/{cap}) for {af}/{model}/a{alpha:02d}. Triggering writeNow.", flush=True)
            with open(cd_path) as f:
                ct = f.read()
            ct = ct.replace("stopAt          endTime;", "stopAt          writeNow;")
            with open(cd_path, "w") as f:
                f.write(ct)
            break
            
    proc.wait()
    wall_time = time.time() - start_time
    
    # 6. Reconstruct
    subprocess.run(["bash", "-c", f"source /opt/openfoam13/etc/bashrc && cd {case_dir} && reconstructPar -latestTime > log.reconstructPar 2>&1"], check=False)
    
    # 7. yPlus
    subprocess.run(["bash", "-c", f"source /opt/openfoam13/etc/bashrc && cd {case_dir} && foamPostProcess -solver incompressibleFluid -func yPlus -latestTime > log.yPlus 2>&1"], check=False)
    
    data = get_force_data(case_dir)
    res = {
        "case": case_dir, "airfoil": af, "model": model, "alpha": float(alpha),
        "wall_time": wall_time, "iterations": 0, "cl": 0.0, "cd": 0.0, "cm": 0.0,
        "yplus_max": parse_yplus(case_dir), "flag": "",
        "bounding_k": count_bounding_k(case_dir),
        "relax_factor": "0.2/0.5" if relax_fallback else "0.3/0.7"
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
            
    print(f"FINISHED FRESH {af}/{model}/a{alpha:02d}: Cl={res['cl']:.5f} Cd={res['cd']:.5f} Cm={res['cm']:.5f} y+={res['yplus_max']:.3f} k_bnd={res['bounding_k']} iters={res['iterations']} flag={res['flag']}", flush=True)
    return res

if __name__ == "__main__":
    import sys
    if os.path.exists("/tmp/stop_sweeps"):
        print("[STOP] Controlled stop active. Not launching new case.", flush=True)
        sys.exit(0)

    af = sys.argv[1]
    model = sys.argv[2]
    alpha = int(sys.argv[3])
    fallback = len(sys.argv) > 4 and sys.argv[4] == "--fallback"
    res = run_single_fresh_case(af, model, alpha, fallback)
    with open(os.path.join(CASES_ROOT, af, model, f"a{alpha:02d}", "result.json"), "w") as f:
        json.dump(res, f, indent=2)
