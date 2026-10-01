#!/bin/bash
#SBATCH --job-name=vc_arc_arm_c
#SBATCH --partition=short
#SBATCH --time=12:00:00
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --signal=B:USR1@900
#SBATCH --output=%x_%j.out
# Scroll 4 whole-scroll tranche, arm (c): arm (a)'s constraints PLUS absolute windings from the index (abs_winding.json).
# Identical to arm_a.sh otherwise. Requires bundle/stage_c.sh -> $DATA/vc_arc/tranche_s4_abs/READY and bundle/patch_abs.sh.
set -euo pipefail
T=$DATA/vc_arc/tranche_s4_abs
[ -f "$T/READY" ] || { echo "FAIL: run bundle/stage_c.sh first ($T/READY missing)"; exit 2; }
source "$T/params.env"
export NUM_WINDINGS=${NUM_WINDINGS:-130} NUM_WINDINGS_SOURCE="${NUM_WINDINGS_SOURCE:-as arm_a}" INIT_DR=${INIT_DR:-32}
export ARM=arm_c ROLES=1 ABS_WINDING=$T/abs_winding.json Z0 Z1 STEPS=${STEPS:-30000} DATASET_TGZ=$T/dataset.tgz DATASET_STRIP=${DATASET_STRIP:-1} UMB=-
exec bash "$DATA/vc_arc/bundle/run_arm.sh"
