# Simulation Pipeline (`simulation/`)

This folder contains only the solver execution scripts required to set up and run the complete OpenFOAM v13 RANS matrix (`NACA 0012`, `NACA 2412`, `NACA 4412` across `SA` and `k-omega SST` at `0, 4, 8, 12, 15 deg`, plus `a08_kfix`).

## Files
- `Allrun` — Master bash script that sources OpenFOAM v13, executes all 31 CFD runs, and triggers post-processing.
- `setup_sweep_case.py` — Generates an individual OpenFOAM case directory (mesh links, rotated freestream BCs, turbulence parameters, `controlDict`).
- `run_sweep.py` — Runs the 15-case continuation sweep for a chosen turbulence model (`SA` or `SST`).
- `run_a08_kfix.py` — Runs the controlled NACA 0012 SST $\alpha = 8^\circ$ limiter-fix case.

## Usage
```bash
# Run the entire 31-case simulation suite + post-processing
chmod +x simulation/Allrun
./simulation/Allrun

# Or run a single model sweep
python3 simulation/run_sweep.py SA
python3 simulation/run_sweep.py SST
```
