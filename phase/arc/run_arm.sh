#!/bin/bash
# SessB-3 shared job body for test_job.sh / arm_a.sh / arm_b.sh (settings from the wrapper: ARM, STEPS, Z0, Z1, UMB,
# optional IDS, ROLES, CKPT_EVERY, KEEP). Works with the route setup.sh chose ($DATA/vc_arc/route.txt):
#   apptainer -> villa.sif ; venv -> $DATA/vc_arc/env (villa's exact uv.lock).
# Stages inputs $DATA -> $SCRATCH, runs villa's unchanged fit_spiral.py, copies checkpoints into $DATA every CKPT_EVERY
# steps (keeping the newest KEEP), resumes from the newest one when resubmitted, writes DONE.
set -euo pipefail
: "${ARM:?}" "${STEPS:?}" "${Z0:?}" "${Z1:?}" "${UMB:?}"
ROOT=${VC_ARC_ROOT:-$DATA/vc_arc}; B=$ROOT/bundle; O=$ROOT/out/$ARM; mkdir -p "$O/ckpt" "$O/logs" "$ROOT/cache/$ARM"
W=${SCRATCH:-${TMPDIR:?no SCRATCH or TMPDIR}}/vc_arc_${ARM}_${SLURM_JOB_ID:-local}; mkdir -p "$W"
CKPT_EVERY=${CKPT_EVERY:-2000}; KEEP=${KEEP:-3}; LOG=$O/logs/job_${SLURM_JOB_ID:-local}.log
exec > >(tee -a "$LOG") 2>&1
say() { echo "[$(date -u +%FT%TZ)] $*"; }
[ -f "$O/DONE" ] && { say "already DONE: $(cat "$O/DONE")"; exit 0; }
[ -f "$ROOT/route.txt" ] || { say "FAIL: $ROOT/route.txt missing: run setup.sh on the login node first"; exit 2; }
kv() { awk -F= -v k="$1" '$1==k{print substr($0, index($0,"=")+1)}' "$ROOT/route.txt"; }
ROUTE=$(kv route); DRV_MIN=$(kv driver_min)
for m in $(kv modules); do module load "$m"; done
say "arm=$ARM steps=$STEPS z=[$Z0,$Z1) route=$ROUTE node=$(hostname) job=${SLURM_JOB_ID:-local} scratch=$W"
ENVS="FIT_SPIRAL_CACHE_DIR=$ROOT/cache/$ARM/villa,TRITON_CACHE_DIR=$ROOT/cache/$ARM/triton,WANDB_MODE=disabled,PYTHONNOUSERSITE=1"
if [ "$ROUTE" = apptainer ]; then
  APPT=$(kv runtime); [ -x "$APPT" ] || APPT=$(command -v apptainer || command -v singularity || true)
  [ -n "$APPT" ] || { say "FAIL: apptainer not found on the compute node"; exit 2; }
  run() { "$APPT" exec --nv --cleanenv --pwd /opt/villa/spiral-fitting -B "$B,$O,$W,$ROOT/cache/$ARM,$ROOT/data" \
            --env "$ENVS" "$ROOT/villa.sif" "$@"; }
else
  run() { ( cd "$ROOT/villa/spiral-fitting" && env ${ENVS//,/ } PATH="$ROOT/env/bin:$PATH" "$@" ); }
fi
if [ -z "${ARC_TEST_NOGPU:-}" ]; then   # test hook (local CI only): skip the GPU checks
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || { say "FAIL: nvidia-smi"; exit 2; }
  DRV=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1 | cut -d. -f1)
  [ "$DRV" -ge "$DRV_MIN" ] || { say "FAIL: NVIDIA driver $DRV < $DRV_MIN for route $ROUTE (see README_ARC.md 'Driver')"; exit 2; }
  run python -c "import torch; assert torch.cuda.is_available(); print('cuda ok', torch.__version__, torch.version.cuda, torch.cuda.get_device_name(0))"
fi

# ---- stage $DATA -> $SCRATCH ----
T=$(date +%s)
run python "$B/make_dataset.py" --zips "$ROOT/data" --out "$W/ds" --umbilicus "$UMB" ${ROLES:+--roles "$ROLES"} ${IDS:+--ids "$IDS"} --z0 "$Z0" --z1 "$Z1"
say "staged in $(( $(date +%s) - T ))s"

# ---- config (SessB protocol overrides; only the PCL gates differ between arms) ----
SessG=false; SAME=false; [ -n "${ROLES:-}" ] && { SessG=true; SAME=true; }
CFG="{\"z_begin\":$Z0,\"z_end\":$Z1,\"optimizer_num_training_steps\":$STEPS,\"input_use_tracks\":false,\"input_use_fibers\":false,\"input_use_fiber_directions\":false,\"input_use_pcl_absolute\":false,\"input_use_pcl_drawn_control_points\":false,\"input_use_normals\":false,\"input_use_gradient_magnitude\":false,\"input_use_winding_inference\":false,\"input_use_outer_shell\":false,\"input_use_pcl_relative\":$SessG,\"input_use_pcl_same_winding\":$SAME}"
echo "$CFG" > "$O/config.json"

# ---- resume from the newest checkpoint in $DATA ----
RESUME=$(ls -1 "$O"/ckpt/step_*.ckpt 2>/dev/null | sort | tail -1 || true)
[ -n "$RESUME" ] && say "resuming from $RESUME"

# ---- checkpoint mirror: villa autosaves $W/run/checkpoint_fitted.ckpt every 1,000 steps ----
sync_ckpt() {   # $1 = force: copy whatever the latest autosave is
  local f=$W/run/checkpoint_fitted.ckpt it
  [ -f "$f" ] || return 0
  it=$(run python "$B/ckpt_iter.py" "$f" 2>/dev/null || echo -1)
  [ "$it" -gt 0 ] || return 0
  if [ "${1:-}" = force ] || [ $(( it % CKPT_EVERY )) -eq 0 ]; then
    local dst=$O/ckpt/step_$(printf %05d "$it").ckpt
    [ -f "$dst" ] || { cp "$f" "$dst.tmp" && mv "$dst.tmp" "$dst" && say "checkpoint -> $dst"; }
    ls -1 "$O"/ckpt/step_*.ckpt | sort | head -n -"$KEEP" | xargs -r rm -f
  fi
  echo "$it" > "$O/progress.txt"
}
trap 'say "USR1: pre-timeout sync"; sync_ckpt force' USR1
trap 'say "TERM: sync"; sync_ckpt force' TERM

cd "$W"
run env FIT_SPIRAL_CONFIG_OVERRIDES="$CFG" FIT_SPIRAL_RUN_DIR="$W/run" FIT_SPIRAL_METRICS_HISTORY="$O/metrics.jsonl" \
    ${RESUME:+FIT_SPIRAL_RESUME_PATH=$RESUME} \
    python -u "${ARC_TEST_FIT:-$B/run_fit.py}" "$O/mem.json" -- --dataset "$W/ds" > "$O/logs/fit_${SLURM_JOB_ID:-local}.log" 2>&1 &
FIT=$!
LAST=""
while kill -0 $FIT 2>/dev/null; do
  sleep "${ARC_POLL:-60}" & wait $! || true
  M=$(stat -c %Y "$W/run/checkpoint_fitted.ckpt" 2>/dev/null || true)
  [ -n "$M" ] && [ "$M" != "$LAST" ] && { sync_ckpt; LAST=$M; }
done
wait $FIT && RC=0 || RC=$?
it=$(run python "$B/ckpt_iter.py" "$W/run/checkpoint_fitted.ckpt" 2>/dev/null || echo -1)
say "fit exit $RC completed_iterations=$it"
if [ "$it" = "$STEPS" ]; then
  cp "$W/run/checkpoint_fitted.ckpt" "$O/final.ckpt.tmp" && mv "$O/final.ckpt.tmp" "$O/final.ckpt"
  ( cd "$W/run" && tar czf "$O/run_small.tgz" --exclude='*.ckpt' . ) || true
  echo "steps=$STEPS sha256=$(sha256sum "$O/final.ckpt" | cut -d' ' -f1) utc=$(date -u +%FT%TZ) job=${SLURM_JOB_ID:-local} route=$ROUTE" > "$O/DONE"
  say "DONE: $(cat "$O/DONE")"; exit 0
fi
sync_ckpt force
say "NOT DONE ($it / $STEPS). Resubmit the same script: it resumes from the newest checkpoint in $O/ckpt."; exit 3
