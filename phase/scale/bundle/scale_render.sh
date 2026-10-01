#!/bin/bash
#SBATCH --job-name=vc_scale_render
#SBATCH --partition=short
#SBATCH --time=06:00:00
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --output=%x_%j.out
# Scale add-on, stage render. Usage (from $DATA/vc_arc/scale): sbatch scale_render.sh arm_a|arm_b
# Body: scale_body.sh (exec'd, so Slurm's signals reach its traps). Last line: exactly "RENDER OK" or "RENDER FAILED: <reason>".
exec bash "${DATA:?DATA unset}/vc_arc/scale/scale_body.sh" render "$@"
