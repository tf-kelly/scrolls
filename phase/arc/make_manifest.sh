#!/bin/bash
# (Build side, not run on ARC.) Write BUNDLE/INPUTS.sha256 with paths relative to $DATA/vc_arc:
#   bundle/<files>, data/<Stevens zips> (setup.sh downloads them), villa.sif (optional; apptainer route only).
# whole_scroll files that do not exist yet are PENDING. Usage: bash make_manifest.sh BUNDLE_DIR SIF ZIPDIR
set -euo pipefail
BD=$1; SIF=$2; Z=$3
{ echo "# sha256  path-relative-to-\$DATA/vc_arc   (SessB-3; PENDING = SessA-12 whole-scroll input not yet produced)"
  ( cd "$BD/.." && for f in run_arm.sh arm_a.sh arm_b.sh test_job.sh setup.sh stage.sh pack_outputs.sh make_dataset.py ckpt_iter.py \
      run_fit.py villa_src.tar devel/umbilicus_slab2.json devel/patch_ids_100.txt; do sha256sum "bundle/$f"; done )
  echo "$(sha256sum "$Z/s4_good_patches.zip" | cut -d' ' -f1)  data/s4_good_patches.zip"
  echo "$(sha256sum "$Z/s4_bad_patches.zip" | cut -d' ' -f1)  data/s4_bad_patches.zip"
  echo "$(sha256sum "$SIF" | cut -d' ' -f1)  villa.sif"
  for f in umbilicus.json same_windings.json relative_windings.json; do
    if [ -f "$BD/whole_scroll/$f" ]; then ( cd "$BD/.." && sha256sum "bundle/whole_scroll/$f" ); else echo "PENDING  bundle/whole_scroll/$f"; fi; done
} > "$BD/INPUTS.sha256"
cat "$BD/INPUTS.sha256"
