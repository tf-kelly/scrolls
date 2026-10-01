#!/bin/bash
#SBATCH --job-name=vc_scale_quilt
#SBATCH --partition=short
#SBATCH --time=06:00:00
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --output=%x_%j.out
# Scale add-on, stage quilt (after scale_flatten.sh ARM). Usage (from $DATA/vc_arc/scale): sbatch scale_quilt.sh arm_a
# Body: scale_body.sh (exec'd, so Slurm's signals reach its traps). Last line: exactly "QUILT OK" or "QUILT FAILED: <reason>".
exec bash "${DATA:?DATA unset}/vc_arc/scale/scale_body.sh" quilt "$@"
