# Comparative Study of Spalart-Allmaras and $k$-$\omega$ SST Models for NACA Airfoils Against NASA Wind Tunnel Data Using OpenFOAM

[![OpenFOAM](https://img.shields.io/badge/OpenFOAM-Foundation%20v13-blue.svg)](https://openfoam.org)
[![Turbulence Models](https://img.shields.io/badge/RANS-SA%20%7C%20k--%CF%89%20SST-orange.svg)](https://turbmodels.larc.nasa.gov)
[![Airfoils](https://img.shields.io/badge/Airfoils-NACA%200012%20%7C%202412%20%7C%204412-success.svg)](docs/final_sweep_report.md)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green.svg)](requirements.txt)

An end-to-end **OpenFOAM v13** computational fluid dynamics (CFD) validation study comparing the **Spalart-Allmaras (SA)** one-equation and **Menter $k$-$\omega$ SST** two-equation RANS turbulence models across three NACA 4-digit airfoils (**NACA 0012**, **NACA 2412**, and **NACA 4412**) against experimental wind-tunnel benchmarks at $\text{Re} = 6.0 \times 10^6$ and $M = 0.15$.

> **Research Team:** Garige Surya Prakash\*, Shaik Faaiq Hussain, Nandam Venkata Prasanna Anjaneyulu  
> **Supervisor & Mentor:** Dr. Yagya Dutta Dwivedi — *Department of Aeronautical Engineering, Institute of Aeronautical Engineering (IARE), Hyderabad, India*

---

## Key Highlights & Engineering Findings

- **Airfoils Studied:** Symmetric **NACA 0012** ($0\%$ camber), moderately cambered **NACA 2412** ($2\%$ camber), and highly cambered **NACA 4412** ($4\%$ camber), all $12\%$ thickness.
- **High-Resolution Low-Re Mesh:** Block-structured $449 \times 129$ C-grid with $500c$ farfield radius and first cell height $y_1 = 4.0 \times 10^{-6}\,\text{m}$, maintaining $y^+_{\max} < 1.0$ (peak $\approx 0.70$) with zero wall functions.
- **Wind-Tunnel Benchmarks:**
  - **NACA 0012:** Ladson (NASA TM 4074, LTPT, tripped at $x/c=0.05$) & Gregory & O'Reilly (ARC R&M 3726, surface $C_p$).
  - **NACA 2412 & NACA 4412:** Abbott & von Doenhoff (NACA TR 824, LTT).
- **Model Verdict:**
  - **Symmetric NACA 0012:** **Spalart-Allmaras** matches NASA LTPT drag within **$2.4\%$** at $\alpha = 8^\circ$ ($C_d = 0.01055$ vs. $0.01050$), whereas SST overpredicts drag by $+31.7\%$ ($0.01383$) on the $449 \times 129$ grid.
  - **Cambered NACA 2412 & 4412:** **Menter $k$-$\omega$ SST** achieves **$>40\%$ lower drag RMS error** than SA ($0.00120$ vs. $0.00215$ on NACA 2412; $0.00132$ vs. $0.00262$ on NACA 4412).
  - **Controlled `a08_kfix` Experiment:** Suppressing `bounding k` warnings by **$99.92\%$** ($2{,}390 \to 2$) shifted $C_d$ by only $+0.00004$ ($0.01383 \to 0.01386$), proving the SST drag offset arises from spatial discretization truncation rather than limiter bounding.

---

## Repository Structure

```text
NACA_CFD_RANS_Models/
├── README.md                          # Project overview, results summary, & usage
├── LICENSE                            # MIT License
├── requirements.txt                   # Python dependencies for post-processing & tests
├── Allrun                             # Root entrypoint (--postprocess default | --full | --verify)
├── reproduce_outputs.sh               # Fast post-processing & figure reproduction script
│
├── simulation/                        # Standalone OpenFOAM v13 simulation runner
│   ├── Allrun                         # Runs all 30 matrix simulations + a08_kfix + post-processing
│   ├── setup_sweep_case.py            # Case generator (mesh, rotated BCs, schemes, controlDict)
│   ├── run_sweep.py                   # 15-case continuation sweep runner (SA / SST)
│   └── run_a08_kfix.py                # Controlled a08_kfix simulation runner
│
├── docs/                              # Technical sweep summary report
│   └── final_sweep_report.md
│
├── data/                              # Experimental & NASA TMR reference datasets
│   ├── exp/                           # Ladson, Abbott & von Doenhoff, Gregory & O'Reilly, McCroskey
│   └── refs/                          # NASA TMR CFL3D SA & SST reference data
│
├── mesh/                              # Structured C-grid source meshes (NACA 0012, 2412, 4412)
├── cases/                             # OpenFOAM v13 simulation matrix (30 cases + a08_kfix)
│
├── scripts/
│   ├── setup/                         # Case generation & OpenFOAM setup utilities
│   ├── sweep/                         # Solver orchestration & controlled k-fix runner
│   └── postprocess/                   # Coefficient extraction, cross-check, & F01-F11 plotters
│
├── results/
│   ├── tables/                        # Validated CSVs, Excel raw coefficients, & final JSON
│   ├── figures/                       # Publication figures F01-F11 (.png & .pdf)
│   ├── paper_figures/                 # Extended report figures & validation suites
│   ├── convergence/                   # Residual & force convergence histories (33 plots)
│   └── cfd_data_export/               # Per-airfoil exported datasets
│
└── tests/
    └── test_project_integrity.py      # Automated deliverable & matrix verification suite
```

---

## Quickstart & Reproduction

### 1. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 2. Regenerate Tables, Cross-Check & Publication Figures (Fast)
```bash
chmod +x Allrun reproduce_outputs.sh
./Allrun --postprocess
```

### 3. Verify Project Integrity
```bash
./Allrun --verify
# or directly:
python3 -m pytest -v tests
```

### 4. Re-run Full OpenFOAM v13 Simulation Matrix (Requires OpenFOAM v13)
```bash
# Option A: Standalone simulation runner
chmod +x simulation/Allrun
./simulation/Allrun

# Option B: Via root entrypoint
./Allrun --full
```

---

## Deliverables Index

- **Sweep Summary Report:** [final_sweep_report.md](docs/final_sweep_report.md)
- **Aerodynamic Coefficients Table (30 Runs):** [table_aerodynamic_coefficients.csv](results/tables/table_aerodynamic_coefficients.csv)
- **Statistical Summary Table:** [table_summary_statistics.csv](results/tables/table_summary_statistics.csv)
- **All Extracted Case Metrics:** [results_all.csv](results/tables/results_all.csv)
