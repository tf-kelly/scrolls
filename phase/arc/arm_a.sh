#!/bin/bash
#SBATCH --job-name=vc_arc_arm_a
#SBATCH --partition=short
#SBATCH --time=12:00:00
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=192G
#SBATCH --signal=B:USR1@900
#SBATCH --output=%x_%j.out
# SessB-3 arm (a): whole-scroll villa Spiral fit WITH our whole-scroll constraints (SessA-12), 30,000 steps.
# Resubmit the same file after a timeout: it resumes from the newest checkpoint in $DATA/vc_arc/out/arm_a/ckpt.
export ARM=arm_a STEPS=30000 Z0=${Z0:-496} Z1=${Z1:-11008}
export UMB=$DATA/vc_arc/bundle/whole_scroll/umbilicus.json ROLES=$DATA/vc_arc/bundle/whole_scroll
exec bash "$DATA/vc_arc/bundle/run_arm.sh"
