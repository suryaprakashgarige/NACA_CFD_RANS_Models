#!/usr/bin/env python3
import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
import sys
import time
import subprocess
import glob
import json
import re
import numpy as np

CASES_ROOT = os.path.join(PROJECT_ROOT, "cases")
SCRIPTS_ROOT = os.path.join(PROJECT_ROOT, "scripts", "sweep")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")

os.makedirs(RESULTS_DIR, exist_ok=True)

def get_force_data(case_dir):
    force_files = sorted(glob.glob(os.path.join(case_dir, "postProcessing", "forceCoeffs", "*", "forceCoeffs.dat")))
    if not force_files:
        return None
    all_lines = []
    for ff in force_files:
        try:
            with open(ff, "r") as f:
                lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
                all_lines.extend(lines)
        except Exception:
            pass
    if not all_lines:
        return None
    try:
        data = []
        for l in all_lines:
            parts = [float(x) for x in l.split()]
            data.append(parts)
        data = sorted(data, key=lambda x: x[0])
        unique_data = []
        seen = set()
        for row in data:
            if row[0] not in seen:
                seen.add(row[0])
                unique_data.append(row)
        return np.array(unique_data)
    except Exception:
        return None

def run_single_sweep_case(case_dir, alpha_deg, ranks=3, check_interval=5):
    is_a15 = (alpha_deg >= 14.5)
    max_iter = 4000 if is_a15 else 2500
    print(f"\n==================================================")
    print(f"RUNNING SWEEP CASE: {case_dir}")
    print(f"  alpha = {alpha_deg} deg | max_iter = {max_iter} | ranks = {ranks}")
    print(f"==================================================")
    start_time = time.time()

    # 1. Decompose if needed
    if not os.path.exists(os.path.join(case_dir, "processor0")):
        cmd_decomp = f"source /opt/openfoam13/etc/bashrc && cd {case_dir} && decomposePar > log.decomposePar 2>&1"
        subprocess.run(["bash", "-c", cmd_decomp], check=True)

    cd_file = os.path.join(case_dir, "system", "controlDict")
    log_file = os.path.join(case_dir, "log.foamRun")
    
    # 2. Run foamRun
    cmd_run = (
        f"source /opt/openfoam13/etc/bashrc && cd {case_dir} && "
        f"mpirun --mca btl_vader_single_copy_mechanism none -np {ranks} foamRun -parallel > log.foamRun 2>&1"
    )
    proc = subprocess.Popen(["bash", "-c", cmd_run])
    print(f"foamRun started (PID {proc.pid}) in {case_dir}")

    plateau_met = False
    
    while proc.poll() is None:
        time.sleep(check_interval)
        data = get_force_data(case_dir)
        if data is None or len(data) < 500:
            continue

        cd_500 = data[-500:, 2]
        cl_500 = data[-500:, 3]
        mean_cd = max(abs(np.mean(cd_500)), 1e-4)
        mean_cl = np.mean(cl_500)
        
        d_cd_pct = (np.max(cd_500) - np.min(cd_500)) / mean_cd * 100
        if abs(mean_cl) > 0.05:
            d_cl_pct = (np.max(cl_500) - np.min(cl_500)) / abs(mean_cl) * 100
        else:
            d_cl_pct = (np.max(cl_500) - np.min(cl_500)) * 100

        # Check relaxed criteria: dCd < 0.5% over 500 and dCl < 0.2% over 500 (or absolute dCl < 0.002)
        cl_cond = (d_cl_pct < 0.2) or (np.max(cl_500) - np.min(cl_500) < 0.002)
        cd_cond = (d_cd_pct < 0.5)

        if cd_cond and cl_cond and not is_a15:
            cur_iter = int(data[-1, 0])
            print(f"\n>>> SWEEP CONVERGENCE MET at Iter {cur_iter}!")
            print(f"    Cd = {data[-1, 2]:.6f}, Cl = {data[-1, 3]:.6f}")
            print(f"    last-500 dCd = {d_cd_pct:.4f}%, last-500 dCl = {d_cl_pct:.4f}%")
            print(f"Issuing graceful stop (stopAt writeNow)...")
            with open(cd_file, "r") as f:
                cur_cd = f.read()
            cur_cd = cur_cd.replace("stopAt          endTime;", "stopAt          writeNow;")
            with open(cd_file, "w") as f:
                f.write(cur_cd)
            plateau_met = True
            break

    proc.wait()
    wall_time = time.time() - start_time
    print(f"Execution finished in {wall_time:.1f} s ({wall_time/60:.2f} min).")

    # Restore stopAt endTime
    if plateau_met:
        with open(cd_file, "r") as f:
            cur_cd = f.read()
        cur_cd = cur_cd.replace("stopAt          writeNow;", "stopAt          endTime;")
        with open(cd_file, "w") as f:
            f.write(cur_cd)

    # Reconstruct
    cmd_reconst = f"source /opt/openfoam13/etc/bashrc && cd {case_dir} && reconstructPar -latestTime > log.reconstructPar 2>&1"
    subprocess.run(["bash", "-c", cmd_reconst], check=False)

    # Post-process yPlus
    cmd_yplus = f"source /opt/openfoam13/etc/bashrc && cd {case_dir} && foamPostProcess -func yPlus -latestTime > log.yPlus 2>&1"
    subprocess.run(["bash", "-c", cmd_yplus], check=False)

    # Extract results
    data = get_force_data(case_dir)
    res = {
        "case": case_dir,
        "airfoil": os.path.basename(os.path.dirname(os.path.dirname(case_dir))),
        "model": os.path.basename(os.path.dirname(case_dir)),
        "alpha": alpha_deg,
        "wall_time": wall_time,
        "iterations": 0,
        "cl": 0.0,
        "cd": 0.0,
        "cm": 0.0,
        "d_cd_500_pct": 0.0,
        "d_cl_500_pct": 0.0,
        "yplus_max": 0.0
    }

    if data is not None and len(data) > 0:
        if is_a15 and len(data) >= 1000:
            # Average last 1000 iterations for alpha=15
            last1000 = data[-1000:]
            res["iterations"] = int(data[-1, 0])
            res["cm"] = float(np.mean(last1000[:, 1]))
            res["cd"] = float(np.mean(last1000[:, 2]))
            res["cl"] = float(np.mean(last1000[:, 3]))
        else:
            res["iterations"] = int(data[-1, 0])
            res["cm"] = float(data[-1, 1])
            res["cd"] = float(data[-1, 2])
            res["cl"] = float(data[-1, 3])

        if len(data) >= 500:
            cd_500 = data[-500:, 2]
            cl_500 = data[-500:, 3]
            res["d_cd_500_pct"] = float((np.max(cd_500) - np.min(cd_500)) / max(abs(np.mean(cd_500)), 1e-4) * 100)
            res["d_cl_500_pct"] = float((np.max(cl_500) - np.min(cl_500)) / max(abs(np.mean(cl_500)), 1e-4) * 100)

    # Read yPlus from reconstructed field
    time_dirs = [d for d in os.listdir(case_dir) if d.replace(".", "").isdigit() and float(d) > 0]
    if time_dirs:
        time_dirs.sort(key=float)
        yp_file = os.path.join(case_dir, time_dirs[-1], "yPlus")
        if os.path.exists(yp_file):
            try:
                with open(yp_file, "r") as ypf:
                    text = ypf.read()
                m = re.search(r"airfoil\s*\{[^}]*?value\s+nonuniform List<scalar>\s*\d+\s*\((.*?)\)", text, re.DOTALL)
                if m:
                    yp_vals = [float(x) for x in m.group(1).split()]
                    res["yplus_max"] = float(max(yp_vals))
            except Exception:
                pass

    print(f"\nCOMPLETED {case_dir}:")
    print(f"  Iter={res['iterations']}, Cl={res['cl']:.6f}, Cd={res['cd']:.6f}, Cm={res['cm']:.6f}, WallTime={res['wall_time']:.1f}s, y+max={res['yplus_max']:.4f}")
    return res

def run_model_chain(model):
    airfoils = ["naca0012", "naca2412", "naca4412"]
    angles = [0.0, 4.0, 8.0, 12.0, 15.0]
    results_file = os.path.join(RESULTS_DIR, f"sweep_results_{model}.json")
    
    chain_results = []
    
    for airfoil in airfoils:
        for i, alpha in enumerate(angles):
            alpha_str = f"a{int(round(alpha)):02d}"
            case_dir = os.path.join(CASES_ROOT, airfoil, model, alpha_str)

            # Determine continuation source according to spec and user rule:
            # (a04 from a00, a08 from a04, a12 from a08, a15 from a12; 2412 from 0012's result, 4412 from 2412's)
            if airfoil == "naca0012":
                if i == 0:
                    prev_case = None  # fresh start
                else:
                    prev_alpha = f"a{int(round(angles[i-1])):02d}"
                    prev_case = os.path.join(CASES_ROOT, "naca0012", model, prev_alpha)
            elif airfoil == "naca2412":
                if i == 0:
                    prev_case = os.path.join(CASES_ROOT, "naca0012", model, "a00")
                else:
                    prev_alpha = f"a{int(round(angles[i-1])):02d}"
                    prev_case = os.path.join(CASES_ROOT, "naca2412", model, prev_alpha)
            elif airfoil == "naca4412":
                if i == 0:
                    prev_case = os.path.join(CASES_ROOT, "naca2412", model, "a00")
                else:
                    prev_alpha = f"a{int(round(angles[i-1])):02d}"
                    prev_case = os.path.join(CASES_ROOT, "naca4412", model, prev_alpha)

            # Setup case with continuation initialization and rotated BCs
            setup_cmd = f"python3 {SCRIPTS_ROOT}/setup_sweep_case.py {airfoil} {model} {alpha}"
            if prev_case:
                setup_cmd += f" {prev_case}"
            print(f"\n--- Setting up {case_dir} ---")
            print(f"Command: {setup_cmd}")
            subprocess.run(["bash", "-c", setup_cmd], check=True)

            # Run case
            res = run_single_sweep_case(case_dir, alpha)
            chain_results.append(res)

            # Save incrementally
            try:
                with open(results_file, "w") as rf:
                    json.dump(chain_results, rf, indent=2)
            except Exception as e:
                print(f"Error saving results: {e}")

    print(f"\n==================================================")
    print(f"*** FINISHED ALL 15 RUNS FOR MODEL: {model} ***")
    print(f"Results written to: {results_file}")
    print(f"==================================================")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: run_coarse_sweep.py <SA|SST>")
        sys.exit(1)
    model = sys.argv[1]
    run_model_chain(model)
