#!/bin/bash
#SBATCH --job-name=vc_scale_place
#SBATCH --partition=short
#SBATCH --time=03:00:00
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --output=%x_%j.out
# Scale add-on, stage place. Usage (from $DATA/vc_arc/scale): sbatch scale_place.sh [arm_a|arm_b]   (default: both, then the comparison)
# Body: scale_body.sh (exec'd, so Slurm's signals reach its traps). Last line: exactly "PLACE OK" or "PLACE FAILED: <reason>".
exec bash "${DATA:?DATA unset}/vc_arc/scale/scale_body.sh" place "$@"
