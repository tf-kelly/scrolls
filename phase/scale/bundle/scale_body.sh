#!/bin/bash
# Shared body of scale_place.sh / scale_flatten.sh / scale_render.sh / scale_ink.sh (they `exec` it, so Slurm's
# signals reach this process and its traps). Usage: scale_body.sh STAGE [ARM]
# Everything lives under $DATA/vc_arc/scale; inputs are read from $DATA/vc_arc (env, villa, route.txt, out/<arm>,
# tranche_s4_whole). Outputs: $DATA/vc_arc/scale/out/<stage>/... The last line is exactly "<STAGE> OK" or
# "<STAGE> FAILED: <reason>".
set -uo pipefail
STAGE=${1:?stage}; ARM=${2:-}
UP=$(echo "$STAGE" | tr a-z A-Z)
ROOT=${VC_ARC_ROOT:-$DATA/vc_arc}; S=$ROOT/scale; O=$S/out
mkdir -p "$O/logs"
LOG=$O/logs/${STAGE}${ARM:+_$ARM}_${SLURM_JOB_ID:-local}.log
exec > >(tee -a "$LOG") 2>&1
say() { echo "[$(date -u +%FT%TZ)] $*"; }
RESULT=""
fin() { local rc=$?; [ -n "$RESULT" ] || RESULT="$UP FAILED: exit $rc (see $LOG)"; sleep 1; echo "$RESULT"; }
trap fin EXIT
trap 'RESULT="$UP FAILED: time limit or cancel (signal)"; exit 143' TERM USR1 INT
fail() { RESULT="$UP FAILED: $*"; exit 1; }

# ---------- environment (as the fit jobs: route.txt from setup.sh, the villa venv) ----------
[ -f "$ROOT/route.txt" ] || fail "$ROOT/route.txt missing (run the fit bundle's setup.sh first)"
kv() { awk -F= -v k="$1" '$1==k{print substr($0, index($0,"=")+1)}' "$ROOT/route.txt"; }
for m in $(kv modules); do module load "$m"; done
[ "$(kv route)" = venv ] || fail "route $(kv route): the scale add-on supports the venv route only"
source "$ROOT/env/bin/activate" || fail "cannot activate $ROOT/env"
CXXR=$(kv cxx); case "$CXXR" in */cc/bin/*) export CXX=$CXXR CC=${CXXR%g++}gcc PATH=$(dirname "$CXXR"):$PATH ;; esac
VS=$ROOT/villa/spiral-fitting
[ -f "$VS/fit_spiral.py" ] || fail "villa source missing at $VS"
export PYTHONPATH=$S${PYTHONPATH:+:$PYTHONPATH} PYTHONNOUSERSITE=1 WANDB_MODE=disabled
export LASAGNA_COMPILE_FLATTEN=0 LASAGNA_FUSED_FLATTEN_ADAM_CLAMP=0   # lasagna's own switches: eager torch, no JIT
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-4}
NCPU=${SLURM_CPUS_PER_TASK:-$(nproc)}; WORKERS=${WORKERS:-$(( NCPU > 2 ? NCPU - 1 : 1 ))}
W=${SCRATCH:-${TMPDIR:-/tmp}}/vc_scale_${STAGE}_${ARM:-all}_${SLURM_JOB_ID:-local}; mkdir -p "$W"
say "stage=$STAGE arm=${ARM:-} node=$(hostname) job=${SLURM_JOB_ID:-local} scratch=$W workers=$WORKERS"
if [ -z "${SCALE_NOGPU:-}" ]; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || fail nvidia-smi
  python -c "import torch; assert torch.cuda.is_available(); print('cuda ok', torch.__version__, torch.cuda.get_device_name(0))" || fail "cuda check"
fi
pym() { if [ -n "${SCALE_TEST_SHIM:-}" ]; then python -u "$SCALE_TEST_SHIM" "$@"; else python -u -m "$@"; fi; }   # test hook (CPU CI only)
( cd "$S" && sha256sum -c --quiet SHA256SUMS ) || fail "bundle files differ from SHA256SUMS"
say "bundle files ok"

# ---------- inputs ----------
T=$ROOT/tranche_s4_whole
DATASET_TGZ=${DATASET_TGZ:-$T/dataset.tgz}; DATASET_STRIP=${DATASET_STRIP:-1}
DS_SUB_A=${DS_SUB_A:-}; DS_SUB_B=${DS_SUB_B:-}      # dataset sub-roots (whole scroll: both arms share the tranche root)
ARM_A=${ARM_A:-arm_a}; ARM_B=${ARM_B:-arm_b}
ckpt_of() { echo "$ROOT/out/$1/final.ckpt"; }
stage_ds() {   # untar the patches (+ constraints, umbilicus) to scratch; echo nothing
  [ -f "$DATASET_TGZ" ] || fail "dataset $DATASET_TGZ missing"
  if [ ! -f "$W/ds/.ok" ]; then
    mkdir -p "$W/ds" && tar -xzf "$DATASET_TGZ" -C "$W/ds" --strip-components="$DATASET_STRIP" || fail "untar $DATASET_TGZ"
    touch "$W/ds/.ok"
  fi
}
stage_umb() {  # flatten/render/ink need only umbilicus.json: extract just that (no 57k patch folders on scratch)
  [ -f "$DATASET_TGZ" ] || fail "dataset $DATASET_TGZ missing"
  if [ ! -f "$W/ds/.ok" ] && [ ! -f "$W/ds/.umb" ]; then
    mkdir -p "$W/ds" && tar -xzf "$DATASET_TGZ" -C "$W/ds" --strip-components="$DATASET_STRIP" --wildcards '*umbilicus.json' \
      || fail "untar umbilicus from $DATASET_TGZ"
    touch "$W/ds/.umb"
  fi
}
ds_of() { if [ "$1" = "$ARM_A" ]; then echo "$W/ds${DS_SUB_A:+/$DS_SUB_A}"; else echo "$W/ds${DS_SUB_B:+/$DS_SUB_B}"; fi; }
umb_of() { echo "$(ds_of "$1")/umbilicus.json"; }
ZBAND=${ZBAND:-5622:5878}   # ink band (plan section 3), frozen; override only for tests
ARMDIR() { case "$1" in "$ARM_A"|"$ARM_B") ;; *) fail "ARM must be $ARM_A or $ARM_B (got '$1')";; esac; }

case "$STAGE" in
place)
  ARMS=${ARM:-"$ARM_A $ARM_B"}
  for a in $ARMS; do ARMDIR "$a"; [ -f "$(ckpt_of "$a")" ] || fail "$(ckpt_of "$a") missing"; done
  stage_ds
  export FIT_SPIRAL_CACHE_DIR=$ROOT/cache/$ARM_A/villa   # reuse the fit's derived-patch cache when present
  for a in $ARMS; do
    say "place $a"
    ( cd "$VS" && pym vc_scale.place arm --arm "$a" --ckpt "$(ckpt_of "$a")" --dataset "$(ds_of "$a")" \
        --pairs-from "$(ds_of "$ARM_A")" --out "$O/place" ) || fail "place arm $a"
  done
  DONE_ARMS=(); for a in "$ARM_A" "$ARM_B"; do [ -f "$O/place/$a/place.json" ] && DONE_ARMS+=("$a"); done
  RS=(); for a in "${DONE_ARMS[@]}"; do [ -f "$ROOT/out/$a/run_small.tgz" ] && RS+=("$a=$ROOT/out/$a/run_small.tgz"); done
  FLAGS=${FLAGS:-$S/flags/unsatisfied_whole.csv}   # checker flags for the flagged/clean split (PLAN addendum 2)
  [ -f "$FLAGS" ] || { say "WARNING: $FLAGS missing: no flagged/clean split"; FLAGS=""; }
  ( cd "$VS" && pym vc_scale.place combine --out "$O/place" --arms "${DONE_ARMS[@]}" ${RS:+--run-small "${RS[@]}"} \
      ${FLAGS:+--flags "$FLAGS"} ) || fail combine
  cat "$O/place/place_table.md"
  python - "$O/place/place_summary.json" <<'PY' || fail "summary line"
import json, sys
s = json.load(open(sys.argv[1])); a = s['arms']
line = ' '.join(f"{k}={v['tolerances']['1']['placed_area3d_cm2']:.2f}/{v['area3d_total_cm2']:.2f}cm2" for k, v in a.items())
print('placed@1vox', line)
PY
  ;;
flatten)
  ARMDIR "$ARM"; [ -f "$(ckpt_of "$ARM")" ] || fail "$(ckpt_of "$ARM") missing"
  stage_umb
  PJ=$O/place/$ARM/place.json; [ -f "$PJ" ] || say "WARNING: $PJ missing: villa's default winding range is used"
  rm -rf "$O/flatten/$ARM"; mkdir -p "$O/flatten/$ARM"
  ( cd "$VS" && pym vc_scale.flatten --ckpt "$(ckpt_of "$ARM")" --umbilicus "$(umb_of "$ARM")" \
      --lasagna-dir "${SCALE_TEST_LASAGNA:-$S/lasagna}" --out "$O/flatten/$ARM" --place-json "$PJ" ) 2>&1 \
      | grep --line-buffered -v -E '"GET /jobs/|^\[lasagna\] [a-z_]+ [0-9]*([1-9]|[1-9]0)/' \
      || fail "flatten $ARM"
  [ -f "$O/flatten/$ARM/flat.tifxyz/x.tif" ] || fail "no flattened surface"
  ;;
render)
  ARMDIR "$ARM"; : "${CT_ZARR:?set CT_ZARR to the base URL of the 7.91 um OME-zarr volume (README_SCALE.md)}"
  stage_umb
  F=$O/flatten/$ARM/flat.tifxyz; [ -f "$F/x.tif" ] || fail "$F missing: run scale_flatten.sh $ARM first"
  Q=$O/place/$ARM/quad_cn.npy; [ -f "$Q" ] || say "WARNING: $Q missing: no support map or crops"
  rm -rf "$O/render/$ARM"
  pym vc_scale.render picture --surface "$F" --volume "$CT_ZARR" --out "$O/render/$ARM" \
      --umbilicus "$(umb_of "$ARM")" --cache "$ROOT/cache/zarr/ct" --workers "$WORKERS" --level "${LEVEL:-2}" \
      --quads "$Q" --crop-px "${CROP_PX:-2048}" || fail "render $ARM"
  ;;
ink)
  ARM=${ARM:-$ARM_A}; ARMDIR "$ARM"
  : "${CT_ZARR:?set CT_ZARR (README_SCALE.md)}"
  stage_umb
  F=$O/flatten/$ARM/flat.tifxyz; [ -f "$F/x.tif" ] || fail "$F missing: run scale_flatten.sh $ARM first"
  I=$O/ink/$ARM; mkdir -p "$I"
  if [ -n "${INK_ZARR:-}" ] && [ "${INK_WHOLE:-1}" = 1 ]; then   # (i) the 3-D ink volume along the whole surface (render_ink's convention)
    say "ink (i): 3-D ink volume, whole surface, ${INK_STEP:-4} vox/px"
    pym vc_scale.render inkzarr --surface "$F" --volume "$INK_ZARR" --axes "${INK_AXES:-yxz}" --out "$I/zarr_whole" \
        --umbilicus "$(umb_of "$ARM")" --cache "$ROOT/cache/zarr/ink" --workers "$WORKERS" --step "${INK_STEP:-4}" || fail "inkzarr whole"
    pym vc_scale.ink_model strips --ink "$I/zarr_whole/ink.png" --name "${ARM}_flat" --out "$I/zarr_whole/ink" || fail strips
  else
    say "route (i) skipped (INK_ZARR unset or INK_WHOLE=0)"
  fi
  say "ink (ii): 65 layers in z band $ZBAND"
  pym vc_scale.render layers --surface "$F" --volume "$CT_ZARR" --out "$I/band" --umbilicus "$(umb_of "$ARM")" \
      --cache "$ROOT/cache/zarr/ct" --workers "$WORKERS" --zband "$ZBAND" ${INK_ZARR:+--ink-volume "$INK_ZARR" --ink-axes "${INK_AXES:-yxz}"} \
      || fail "band layers"
  if [ -n "${INK_CKPT_URL:-}" ]; then
    : "${INK_CKPT_SHA256:?set INK_CKPT_SHA256 with INK_CKPT_URL}"
    D=$S/pydeps; UVB=$(command -v uv || echo "$ROOT/tools/uv")
    if ! PYTHONPATH=$D python -c "import timesformer_pytorch, einops" 2>/dev/null; then
      "$UVB" pip install --python "$(command -v python)" --target "$D" --no-deps --require-hashes -r "$S/req_ink.txt" || fail "pip ink deps"
    fi
    CK=$ROOT/cache/ink_model.ckpt
    if [ ! -f "$CK" ] || [ "$(sha256sum "$CK" | cut -d' ' -f1)" != "$INK_CKPT_SHA256" ]; then
      curl -fsSL --retry 3 -o "$CK.part" "$INK_CKPT_URL" && mv "$CK.part" "$CK" || fail "ink model download"
    fi
    [ "$(sha256sum "$CK" | cut -d' ' -f1)" = "$INK_CKPT_SHA256" ] || fail "ink model sha256 mismatch"
    PYTHONPATH=$D:$PYTHONPATH pym vc_scale.ink_model infer --layers "$I/band" --ckpt "$CK" --out "$I/model" \
        --stride "${INK_STRIDE:-32}" ${INK_MAX_TILES:+--max-tiles "$INK_MAX_TILES"} || fail "ink model"
    if [ -f "$I/band/ink_zarr_band.tif" ]; then
      pym vc_scale.ink_model concord --pred "$I/model/pred.tif" --zarr-ink "$I/band/ink_zarr_band.tif" \
          --mask "$I/band/mask.tif" --out "$I/model" || fail concordance
    fi
  else
    say "INK_CKPT_URL unset: team-model inference skipped"
  fi
  if [ -n "${INK_METRICS_MODEL:-}" ] && [ -d "$I/zarr_whole/ink" ]; then   # villa's own scalar (optional)
    D2=$S/pydeps_metrics; UVB=$(command -v uv || echo "$ROOT/tools/uv")
    PYTHONPATH=$D2 python -c "import nnunetv2" 2>/dev/null || "$UVB" pip install --python "$(command -v python)" --target "$D2" nnunetv2 huggingface_hub matplotlib || fail "pip metrics deps"
    ( cd "$VS" && PYTHONPATH=$D2:$PYTHONPATH python -u get_ink_metrics.py "$I/zarr_whole/ink" --output "$I/metrics" \
        --model "$INK_METRICS_MODEL" --pixel-size-um "$(python -c "print(${INK_STEP:-4}*7.91)")" ) || fail "get_ink_metrics"
  fi
  ;;
quilt)
  ARMDIR "$ARM"; : "${CT_ZARR:?set CT_ZARR (README_SCALE.md)}"
  stage_ds
  SRC=$O/flatten/$ARM/source/spiral-checkpoint.tifxyz
  [ -f "$SRC/x.tif" ] || fail "$SRC missing: run scale_flatten.sh $ARM first (the fill uses its fitted surface)"
  WRAP_INDEX=${WRAP_INDEX:-$S/flags/wrap_index_whole.csv}; FLAGS=${FLAGS:-$S/flags/unsatisfied_whole.csv}
  [ -f "$WRAP_INDEX" ] && [ -f "$FLAGS" ] || fail "index/flags missing ($WRAP_INDEX, $FLAGS)"
  Q=$O/quilt/$ARM; rm -rf "$Q"; mkdir -p "$Q"
  say "quilt build (index $(basename "$WRAP_INDEX"), flags $(basename "$FLAGS"))"
  python -u -m vc_scale.quilt build --dataset "$(ds_of "$ARM_A")" --wrap-index "$WRAP_INDEX" --flags "$FLAGS" \
      --fit-source "$SRC" --out "$Q/build" || fail "quilt build"
  cat "$Q/build/quilt_table.md" | tail -8
  say "quilt flatten"
  ( cd "$VS" && pym vc_scale.flatten --surface "$Q/build/concat.tifxyz" --lasagna-dir "${SCALE_TEST_LASAGNA:-$S/lasagna}" \
      --out "$Q/flatten" ) 2>&1 | grep --line-buffered -v -E '"GET /jobs/|^\[lasagna\] [a-z_]+ [0-9]*([1-9]|[1-9]0)/' \
      || fail "quilt flatten"
  say "quilt render"
  python -u -m vc_scale.render picture --surface "$Q/flatten/flat.tifxyz" --volume "$CT_ZARR" --out "$Q/render" \
      --umbilicus "$(umb_of "$ARM_A")" --cache "$ROOT/cache/zarr/ct" --workers "$WORKERS" --level "${LEVEL:-2}" \
      --labels "$Q/build/labels_pts.npy" --crop-px "${CROP_PX:-2048}" || fail "quilt render"
  ;;
snap)
  ARMDIR "$ARM"; : "${CT_ZARR:?set CT_ZARR (README_SCALE.md)}"
  stage_ds
  SRC=$O/flatten/$ARM/source/spiral-checkpoint.tifxyz
  [ -f "$SRC/x.tif" ] || fail "$SRC missing: run scale_flatten.sh $ARM first"
  WRAP_INDEX=${WRAP_INDEX:-$S/flags/wrap_index_whole.csv}; FLAGS=${FLAGS:-$S/flags/unsatisfied_whole.csv}
  Q=$O/quilt/$ARM
  B=$Q/build_snap
  if [ ! -f "$B/quilt.json" ] || [ ! -f "$(ls -d "$B"/windings/w* 2>/dev/null | head -1)/rfit.tif" ]; then
    say "quilt build for snap (same inputs as the quilt stage; also writes r/rfit per winding) -> $B"
    rm -rf "$B"
    python -u -m vc_scale.quilt build --dataset "$(ds_of "$ARM_A")" --wrap-index "$WRAP_INDEX" --flags "$FLAGS" \
        --fit-source "$SRC" --out "$B" || fail "quilt build for snap"
  fi
  say "snap (level ${SNAP_LEVEL:-1}; per-winding outputs in $Q/snap/windings as completed)"
  python -u -m vc_scale.snap --build "$B" --dataset "$(ds_of "$ARM_A")" --volume "$CT_ZARR" --out "$Q/snap" \
      --level "${SNAP_LEVEL:-1}" --heldout-max "${SNAP_HELDOUT_MAX:-3000000}" --mem-chunks "${SNAP_MEM_CHUNKS:-4000}" \
      || fail "snap"
  tail -14 "$Q/snap/snap_table.md"
  ;;
*) fail "unknown stage $STAGE" ;;
esac
say "outputs in $O/$STAGE${ARM:+/$ARM}"
RESULT="$UP OK"
