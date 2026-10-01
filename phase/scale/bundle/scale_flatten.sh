#!/bin/bash
#SBATCH --job-name=vc_scale_flatten
#SBATCH --partition=short
#SBATCH --time=08:00:00
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --output=%x_%j.out
# Scale add-on, stage flatten. Usage (from $DATA/vc_arc/scale): sbatch scale_flatten.sh arm_a|arm_b
# Body: scale_body.sh (exec'd, so Slurm's signals reach its traps). Last line: exactly "FLATTEN OK" or "FLATTEN FAILED: <reason>".
exec bash "${DATA:?DATA unset}/vc_arc/scale/scale_body.sh" flatten "$@"
