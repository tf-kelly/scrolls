#!/bin/bash
#SBATCH --job-name=vc_arc_arm_a2
#SBATCH --partition=short
#SBATCH --time=12:00:00
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --signal=B:USR1@900
#SBATCH --output=%x_%j.out
# Scroll 4 whole-scroll tranche, redo: arm (a2) WITH winding constraints. Cap and initial spacing from tranche_s4_cap/params.env.
# Requires bundle/stage_cap.sh -> $DATA/vc_arc/tranche_s4_cap/READY and bundle/patch_initdr.sh.
set -euo pipefail
T=$DATA/vc_arc/tranche_s4_cap
[ -f "$T/READY" ] || { echo "FAIL: run bundle/stage_cap.sh first ($T/READY missing)"; exit 2; }
source "$T/params.env"
export NUM_WINDINGS NUM_WINDINGS_SOURCE INIT_DR
export ARM=arm_a2 ROLES=1 Z0 Z1 STEPS=${STEPS:-30000} DATASET_TGZ=$T/dataset.tgz DATASET_STRIP=${DATASET_STRIP:-1} UMB=-
exec bash "$DATA/vc_arc/bundle/run_arm.sh"
