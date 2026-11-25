#!/usr/bin/env bash
# ==============================================================================
# reproduce_outputs.sh — Fast Post-Processing & Publication Figure Reproduction
# Extracts aerodynamic coefficients, y+, Cp, cross-checks paper values,
# and regenerates Figures F01-F11 (300 DPI PNG + Vector PDF).
# ==============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "================================================================="
echo "  EDP_CFD_NACA — Reproducing Tables, Cross-Check & Figures"
echo "  Project Root: $PROJECT_ROOT"
echo "================================================================="

echo "[1/3] Extracting CFD forces, y+, and surface Cp..."
python3 "$PROJECT_ROOT/scripts/postprocess/step1_extract.py"

echo "[2/3] Running cross-check & generating summary CSV tables..."
python3 "$PROJECT_ROOT/scripts/postprocess/step2_and_step4.py"

echo "[3/3] Rendering publication figures F01-F11 (PNG + PDF)..."
python3 "$PROJECT_ROOT/scripts/postprocess/step3_plots.py"

echo "================================================================="
echo "  [OK] Outputs updated in results/tables/, results/figures/, docs/"
echo "================================================================="
