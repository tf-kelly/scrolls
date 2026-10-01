#!/bin/bash
# SessB-3: one tarball per finished arm, for the project owner to upload. Contents: DONE, final.ckpt, config.json, mem.json,
# metrics.jsonl, progress.txt, run_small.tgz (villa's small run outputs), logs/. Intermediate checkpoints are left out.
# Usage: bash $DATA/vc_arc/bundle/pack_outputs.sh   -> $DATA/vc_arc/upload/vc_arc_<arm>.tar (+ .sha256)
set -euo pipefail
R=${VC_ARC_ROOT:-$DATA/vc_arc}; U=$R/upload; mkdir -p "$U"; n=0
for arm in arm_a arm_b; do
  O=$R/out/$arm
  if [ ! -f "$O/DONE" ]; then echo "$arm: not DONE (progress: $(cat "$O/progress.txt" 2>/dev/null || echo none)); skipped"; continue; fi
  ( cd "$R/out" && tar cf "$U/vc_arc_$arm.tar" --exclude="$arm/ckpt" "$arm" )
  ( cd "$U" && sha256sum "vc_arc_$arm.tar" > "vc_arc_$arm.tar.sha256" )
  echo "$arm: $(du -h "$U/vc_arc_$arm.tar" | cut -f1)  $(cat "$U/vc_arc_$arm.tar.sha256")"; n=$((n+1))
done
echo "packed $n arm(s) into $U"
