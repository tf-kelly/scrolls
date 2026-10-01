#!/bin/bash
#SBATCH --job-name=vc_arc_test
#SBATCH --partition=devel
#SBATCH --time=00:10:00
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x_%j.out
# SessB-3 test job (<= 10 min): the route setup.sh chose loads, CUDA works on an H100, a 100-patch subset of slab 2
# stages and fits for 50 steps (no constraints, slab-2 umbilicus, z [4096, 4864)). Success line: "TEST JOB PASS".
export ARM=test STEPS=50 Z0=4096 Z1=4864 CKPT_EVERY=50 KEEP=1
export UMB=$DATA/vc_arc/bundle/devel/umbilicus_slab2.json IDS=$DATA/vc_arc/bundle/devel/patch_ids_100.txt ROLES=
rm -rf "$DATA/vc_arc/out/test"          # the test job always starts fresh
bash "$DATA/vc_arc/bundle/run_arm.sh" && echo "TEST JOB PASS" || { echo "TEST JOB FAIL (see $DATA/vc_arc/out/test/logs/)"; exit 1; }
