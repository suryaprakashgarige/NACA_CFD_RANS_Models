#!/usr/bin/env python3
import os
import sys
import time
import subprocess
import glob
import numpy as np
import re

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

def run_case_with_plateau(case_dir, ranks=3, check_interval=3):
    is_a10 = "a10" in case_dir
    print(f"==================================================")
    print(f"Starting case: {case_dir}")
    if is_a10:
        print(f"Binding criterion: STRICT PRIMARY FORCE PLATEAU (< 0.05% over 300 iters)")
    else:
        print(f"Binding criterion: FORCE PLATEAU (< 0.05% over 300 iters OR < 0.5% over 500 iters)")
    print(f"==================================================")
    start_time = time.time()
    
    # 1. Check decomposition
    if not os.path.exists(os.path.join(case_dir, "processor0")):
        print(f"Decomposing case across {ranks} processors...")
        cmd_decomp = f"source /opt/openfoam13/etc/bashrc && cd {case_dir} && decomposePar > log.decomposePar 2>&1"
        subprocess.run(["bash", "-c", cmd_decomp], check=True)

    # 2. Configure controlDict
    cd_file = os.path.join(case_dir, "system", "controlDict")
    with open(cd_file, "r") as f:
        cd_content = f.read()

    lines = cd_content.splitlines()
    in_functions = False
    new_lines = []
    for l in lines:
        if "functions" in l:
            in_functions = True
        if in_functions:
            new_lines.append(l)
        else:
            if l.strip().startswith("writeInterval"):
                new_lines.append("writeInterval   10000;")
            elif l.strip().startswith("purgeWrite"):
                new_lines.append("purgeWrite      1;")
            elif l.strip().startswith("stopAt"):
                new_lines.append("stopAt          endTime;")
            else:
                new_lines.append(l)
    cd_content = "\n".join(new_lines) + "\n"

    # Ensure forceCoeffs writeInterval is 1
    pattern = r"(forceCoeffs\s*\{[^}]*?writeInterval\s+)\d+;"
    cd_content = re.sub(pattern, r"\g<1>1;", cd_content, flags=re.DOTALL)

    with open(cd_file, "w") as f:
        f.write(cd_content)

    log_file = os.path.join(case_dir, "log.foamRun")
    plateau_met = False
    
    while not plateau_met:
        # Launch foamRun
        cmd_run = (
            f"source /opt/openfoam13/etc/bashrc && cd {case_dir} && "
            f"mpirun --mca btl_vader_single_copy_mechanism none -np {ranks} foamRun -parallel >> log.foamRun 2>&1"
        )
        proc = subprocess.Popen(["bash", "-c", cmd_run])
        print(f"foamRun running (PID {proc.pid}) in {case_dir}...")

        while proc.poll() is None:
            time.sleep(check_interval)
            
            data = get_force_data(case_dir)
            if data is None or len(data) < 300:
                continue

            cd_all = data[:, 2]
            cl_all = data[:, 3]
            
            # Window 300
            cd_300 = cd_all[-300:]
            cl_300 = cl_all[-300:]
            mean_cd_300 = max(abs(np.mean(cd_300)), 1e-4)
            d_cd_300_pct = (np.max(cd_300) - np.min(cd_300)) / mean_cd_300 * 100
            d_cl_300 = np.max(cl_300) - np.min(cl_300)

            # Window 500 if available
            d_cd_500_pct = 999.0
            if len(data) >= 500:
                cd_500 = cd_all[-500:]
                d_cd_500_pct = (np.max(cd_500) - np.min(cd_500)) / max(abs(np.mean(cd_500)), 1e-4) * 100

            # Check p and Ux residual < 1e-5
            p_conv = False
            ux_conv = False
            if os.path.exists(log_file):
                try:
                    with open(log_file, "r") as lf:
                        tail_log = lf.readlines()[-40:]
                    for tl in tail_log:
                        if "Solving for p" in tl and "Initial residual =" in tl:
                            val = float(tl.split("Initial residual =")[1].split(",")[0].strip())
                            if val < 1.0e-05:
                                p_conv = True
                        if "Solving for Ux" in tl and "Initial residual =" in tl:
                            val = float(tl.split("Initial residual =")[1].split(",")[0].strip())
                            if val < 1.0e-05:
                                ux_conv = True
                except Exception:
                    pass

            # Plateau criteria:
            if is_a10:
                # STRICT PRIMARY PLATEAU ONLY for a10
                is_flat = (d_cd_300_pct < 0.05)
            else:
                is_flat = (d_cd_300_pct < 0.05) or (d_cd_500_pct < 0.5 and d_cd_300_pct < 0.1)
            
            if is_flat and p_conv and ux_conv:
                cur_iter = int(data[-1, 0])
                print(f"\n>>> FORCE PLATEAU CONFIRMED at Iter {cur_iter}!")
                print(f"    Cd = {cd_all[-1]:.6f}, Cl = {cl_all[-1]:.6f}")
                print(f"    last-300 dCd = {d_cd_300_pct:.4f}%, last-500 dCd = {d_cd_500_pct:.4f}%")
                print(f"    p < 1e-5: {p_conv}, Ux < 1e-5: {ux_conv}")
                print(f"Issuing graceful stop (stopAt writeNow;)...")
                with open(cd_file, "r") as f:
                    cur_cd = f.read()
                cur_cd = cur_cd.replace("stopAt          endTime;", "stopAt          writeNow;")
                with open(cd_file, "w") as f:
                    f.write(cur_cd)
                plateau_met = True
                break

        proc.wait()
        
        # If foamRun ended but plateau was NOT met, check why
        if not plateau_met:
            print("foamRun exited, checking if force plateau was met...")
            data = get_force_data(case_dir)
            if is_a10:
                if data is not None and len(data) >= 300:
                    cd_300 = data[-300:, 2]
                    d_cd_300_pct = (np.max(cd_300) - np.min(cd_300)) / max(abs(np.mean(cd_300)), 1e-4) * 100
                    if d_cd_300_pct < 0.05:
                        print(f"Primary force plateau met for a10: last-300 dCd = {d_cd_300_pct:.4f}% < 0.05%!")
                        plateau_met = True
                        break
                    else:
                        print(f"a10 primary plateau NOT met (last-300 dCd = {d_cd_300_pct:.4f}% >= 0.05%). Extending run...")
            else:
                if data is not None and len(data) >= 500:
                    cd_500 = data[-500:, 2]
                    d_cd_500_pct = (np.max(cd_500) - np.min(cd_500)) / max(abs(np.mean(cd_500)), 1e-4) * 100
                    if d_cd_500_pct < 0.5:
                        print(f"Force plateau met on exit: last-500 dCd = {d_cd_500_pct:.4f}% < 0.5%!")
                        plateau_met = True
                        break

            if not plateau_met:
                print("Continuing/extending run from latestTime...")
                with open(cd_file, "r") as f:
                    cur_cd = f.read()
                cur_cd = cur_cd.replace("stopAt          writeNow;", "stopAt          endTime;")
                cur_cd = re.sub(r"startFrom\s+\w+;", "startFrom       latestTime;", cur_cd)
                cur_cd = re.sub(r"endTime\s+(\d+);", lambda m: f"endTime         {int(m.group(1))+1000};", cur_cd)
                with open(cd_file, "w") as f:
                    f.write(cur_cd)

    # Simulation done and plateau met
    wall_time = time.time() - start_time
    print(f"Case finished in {wall_time:.1f} s ({wall_time/60:.2f} min). Reconstructing latest time...")

    # Restore stopAt endTime
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
    results = {
        "case": case_dir,
        "wall_time": wall_time,
        "iterations": 0,
        "cl": 0.0,
        "cd": 0.0,
        "cm": 0.0,
        "delta_cd_300": 0.0,
        "delta_cd_500": 0.0,
        "delta_cl_300": 0.0,
        "yplus_max": 0.0
    }

    data = get_force_data(case_dir)
    if data is not None and len(data) > 0:
        last = data[-1]
        results["iterations"] = int(last[0])
        results["cm"] = last[1]
        results["cd"] = last[2]
        results["cl"] = last[3]

        if len(data) >= 300:
            cd_300 = data[-300:, 2]
            cl_300 = data[-300:, 3]
            results["delta_cd_300"] = (np.max(cd_300) - np.min(cd_300)) / max(abs(np.mean(cd_300)), 1e-4) * 100
            results["delta_cl_300"] = np.max(cl_300) - np.min(cl_300)
        if len(data) >= 500:
            cd_500 = data[-500:, 2]
            results["delta_cd_500"] = (np.max(cd_500) - np.min(cd_500)) / max(abs(np.mean(cd_500)), 1e-4) * 100

    log_yplus = os.path.join(case_dir, "log.yPlus")
    if os.path.exists(log_yplus):
        with open(log_yplus, "r") as f:
            for l in f:
                if "patch airfoil y+ :" in l:
                    parts = l.split("max =")
                    if len(parts) > 1:
                        results["yplus_max"] = float(parts[1].split()[0])

    print(f"\n==================================================")
    print(f"CASE COMPLETED: {case_dir}")
    print(f"  Iterations: {results['iterations']}")
    print(f"  Wall time:  {results['wall_time']:.1f} s ({results['wall_time']/60:.2f} min)")
    print(f"  Cl:         {results['cl']:.6f}")
    print(f"  Cd:         {results['cd']:.6f}")
    print(f"  Cm:         {results['cm']:.6f}")
    print(f"  delta_Cd (last 300): {results['delta_cd_300']:.4f}%")
    print(f"  delta_Cd (last 500): {results['delta_cd_500']:.4f}%")
    print(f"  y+ max:     {results['yplus_max']:.4f}")
    print(f"==================================================")
    return results

if __name__ == "__main__":
    case_path = sys.argv[1]
    run_case_with_plateau(case_path)
