"""Automated deliverable & data integrity tests for EDP_CFD_NACA."""

from pathlib import Path
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "cases"
RESULTS_DIR = ROOT / "results"
TABLES_DIR = RESULTS_DIR / "tables"
FIGS_DIR = RESULTS_DIR / "figures"
DOCS_DIR = ROOT / "docs"

AIRFOILS = ["naca0012", "naca2412", "naca4412"]
MODELS = ["SA", "SST"]
ALPHAS = ["a00", "a04", "a08", "a12", "a15"]


def test_core_directory_structure():
    """Verify required top-level directories and files exist."""
    for rel in [
        "README.md",
        "LICENSE",
        "requirements.txt",
        "Allrun",
        "reproduce_outputs.sh",
        "docs/Research_Paper_NACA_Airfoils_CFD_Validation.pdf",
        "docs/Research_Paper_NACA_Airfoils_CFD_Validation.docx",
        "docs/final_sweep_report.md",
        "docs/step2_crosscheck_report.md",
    ]:
        assert (ROOT / rel).exists(), f"Missing required deliverable: {rel}"


def test_all_matrix_cases_present_and_clean():
    """Verify all 30 matrix cases + a08_kfix exist without leftover processor* dirs."""
    expected_cases = [
        CASES_DIR / af / model / alpha
        for af in AIRFOILS
        for model in MODELS
        for alpha in ALPHAS
    ]
    expected_cases.append(CASES_DIR / "naca0012" / "SST" / "a08_kfix")

    for cdir in expected_cases:
        assert cdir.is_dir(), f"Missing case directory: {cdir}"
        assert (cdir / "log.foamRun").is_file(), f"Missing log.foamRun in {cdir}"
        assert (cdir / "postProcessing" / "forceCoeffs").is_dir(), f"Missing forceCoeffs in {cdir}"
        proc_dirs = list(cdir.glob("processor*"))
        assert not proc_dirs, f"Leftover parallel processor dirs in {cdir}: {proc_dirs}"


def test_results_tables_complete():
    """Verify extracted CSV tables have expected rows and non-empty metrics."""
    results_csv = TABLES_DIR / "results_all.csv"
    coeff_csv = TABLES_DIR / "table_aerodynamic_coefficients.csv"
    stats_csv = TABLES_DIR / "table_summary_statistics.csv"
    cp_csv = TABLES_DIR / "cp_0012_a00.csv"
    yplus_csv = TABLES_DIR / "yplus.csv"

    for p in [results_csv, coeff_csv, stats_csv, cp_csv, yplus_csv]:
        assert p.is_file(), f"Missing table: {p}"

    df_res = pd.read_csv(results_csv)
    assert len(df_res) == 31, f"Expected 31 cases (30 matrix + a08_kfix), got {len(df_res)}"
    assert set(df_res["airfoil"].unique()) == {"naca0012", "naca2412", "naca4412"}

    df_coeff = pd.read_csv(coeff_csv)
    assert len(df_coeff) == 15, f"Expected 15 airfoil-alpha rows, got {len(df_coeff)}"


def test_publication_figures_complete():
    """Verify all 11 publication figures (F01-F11) exist in both PNG and PDF."""
    expected_stems = [
        "F01_airfoil_geometry",
        "F02_computational_mesh",
        "F03_wall_yplus",
        "F04_lift_curve",
        "F05_drag_curve",
        "F06_drag_polar",
        "F07_surface_pressure",
        "F08_pitching_moment",
        "F09_flow_field_alpha15",
        "F10_eddy_viscosity_ratio_alpha08",
        "F11_a08_kfix_convergence",
    ]
    for stem in expected_stems:
        assert (FIGS_DIR / f"{stem}.png").is_file(), f"Missing {stem}.png"
        assert (FIGS_DIR / f"{stem}.pdf").is_file(), f"Missing {stem}.pdf"


def test_crosscheck_report_has_zero_mismatches():
    """Verify step2_crosscheck_report.md reports zero mismatches."""
    text = (DOCS_DIR / "step2_crosscheck_report.md").read_text(encoding="utf-8")
    assert "Zero mismatches detected" in text
