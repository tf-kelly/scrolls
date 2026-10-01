#!/bin/bash
# SessB-3 one-time setup on the ARC LOGIN node (it has internet; compute nodes are assumed not to).
# Chooses the runtime route and records it in $DATA/vc_arc/route.txt for test_job.sh / arm_a.sh / arm_b.sh:
#   apptainer : apptainer/singularity is available (PATH or `module load`) AND villa.sif is present or SIF_URL is given.
#               The image ships torch 2.11.0 built for CUDA 13.0 (driver >= 580); see BUILD_RECORD.json.
#   venv      : otherwise. Installs uv + Python 3.14 under $DATA/vc_arc and runs villa's own `uv sync --frozen`
#               (the EXACT lock, torch 2.11.0+cu128) into $DATA/vc_arc/env. Downloads happen here only.
# Also fetches Stevens' public patch zips (sha256-checked) and unpacks villa's source (f4570bf).
# Usage (from the unpacked bundle):  bash setup.sh        optional: SIF_URL='<url of villa.sif>' bash setup.sh
# Last line printed: exactly "SETUP OK", or "SETUP FAILED: <reason>".
set -uo pipefail
R=${VC_ARC_ROOT:-$DATA/vc_arc}; B=$R/bundle; mkdir -p "$R/data" "$R/tools" "$R/out" "$R/cache"
fail() { echo "SETUP FAILED: $*"; exit 1; }
say() { echo "[setup $(date -u +%H:%M:%S)] $*"; }
[ -f "$B/INPUTS.sha256" ] || fail "bundle not found at $B (unpack vc_arc_bundle.tar into $R first)"
ZIPURL=https://dl.ash2txt.org/community-uploads/will
sha() { sha256sum "$1" | cut -d' ' -f1; }
want() { awk -v f="$1" '$2==f{print $1}' "$B/INPUTS.sha256"; }   # INPUTS.sha256 paths are relative to $R

# 1. bundle files
bad=$(cd "$R" && awk '$1!~/^(#|PENDING)/ && $2~/^bundle\//{print $1"  "$2}' bundle/INPUTS.sha256 | sha256sum -c --quiet 2>&1) || fail "bundle files differ from INPUTS.sha256: $bad"
say "bundle files ok"

# 2. patch zips (public; W. Stevens' community upload)
for z in s4_good_patches.zip s4_bad_patches.zip; do
  f=$R/data/$z
  if [ ! -f "$f" ] || [ "$(sha "$f")" != "$(want data/$z)" ]; then
    say "downloading $z"; curl -fL --retry 3 -o "$f.part" "$ZIPURL/$z" && mv "$f.part" "$f" || fail "download $z"
  fi
  [ "$(sha "$f")" = "$(want data/$z)" ] || fail "$z sha256 mismatch"
done
say "patch zips ok"

# 3. villa source (compute nodes cannot clone)
if [ ! -f "$R/villa/VILLA_COMMIT" ]; then
  rm -rf "$R/villa"; mkdir -p "$R/villa"; tar -xf "$B/villa_src.tar" -C "$R/villa" || fail "unpack villa_src.tar"
  echo f4570bfa6c2b357fd24a17b46f8a43becf87ea8d > "$R/villa/VILLA_COMMIT"
fi
say "villa source ok ($(cat "$R/villa/VILLA_COMMIT"))"

# 4. route
MODS=""; rm -f "$R/route.txt"
APPT=$(command -v apptainer || command -v singularity || true)
if [ -z "$APPT" ] && command -v module >/dev/null 2>&1; then
  for m in Apptainer apptainer Singularity singularity; do
    if module load "$m" >/dev/null 2>&1; then APPT=$(command -v apptainer || command -v singularity || true); [ -n "$APPT" ] && { MODS="$m"; break; }; fi
  done
fi
if [ -n "$APPT" ] && { [ -f "$R/villa.sif" ] || [ -n "${SIF_URL:-}" ]; }; then
  if [ ! -f "$R/villa.sif" ] || [ "$(sha "$R/villa.sif")" != "$(want villa.sif)" ]; then
    say "downloading villa.sif (3.6 GB)"; curl -fL --retry 3 -o "$R/villa.sif.part" "$SIF_URL" && mv "$R/villa.sif.part" "$R/villa.sif" || fail "download villa.sif"
  fi
  [ "$(sha "$R/villa.sif")" = "$(want villa.sif)" ] || fail "villa.sif sha256 mismatch"
  if "$APPT" exec --cleanenv --pwd /opt/villa/spiral-fitting "$R/villa.sif" python -W ignore -c \
      "import torch, vc_spiral.surface_index, fit_spiral; print('image imports ok', torch.__version__)"; then
    printf 'route=apptainer\nruntime=%s\nmodules=%s\nsif=%s\ndriver_min=580\n' "$APPT" "$MODS" "$R/villa.sif" > "$R/route.txt"
  else
    say "apptainer exec of villa.sif failed on this system: falling back to the venv route"; APPT=""; MODS=""; FELL=1
  fi
fi
if [ ! -f "$R/route.txt" ] || ! grep -q '^route=apptainer' "$R/route.txt"; then
  [ -n "$APPT" ] && say "apptainer found ($APPT) but no villa.sif / SIF_URL: using the venv route"
  [ -z "$APPT" ] && [ -z "${FELL:-}" ] && say "no apptainer/singularity (PATH or module): using the venv route"
  # a C++23-capable compiler for villa's nanobind extension (and a C compiler for triton at run time)
  gver() { g++ -dumpversion 2>/dev/null | cut -d. -f1; }
  if [ "$(gver || echo 0)" -lt 11 ] && command -v module >/dev/null 2>&1; then
    for m in $(module -t avail GCC 2>&1 | grep -E '^GCC/1[1-9]' | sort -V -r); do module load "$m" >/dev/null 2>&1 && [ "$(gver)" -ge 11 ] && { MODS="$m"; break; }; done
  fi
  [ "$(gver || echo 0)" -ge 11 ] || fail "need g++ >= 11 (found $(gver || echo none)); load a GCC >= 11 module and rerun"
  export UV_INSTALL_DIR=$R/tools/bin UV_NO_MODIFY_PATH=1 UV_PYTHON_INSTALL_DIR=$R/python UV_CACHE_DIR=$R/uvcache
  if [ ! -x "$R/tools/bin/uv" ]; then curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null || fail "uv install"; fi
  export PATH=$R/tools/bin:$PATH
  ( cd "$R/villa/spiral-fitting" && UV_PROJECT_ENVIRONMENT=$R/env uv sync --frozen --python 3.14 ) || fail "uv sync --frozen (villa lock)"
  uv pip install -q --python "$R/env/bin/python" pandas || fail "pandas"
  ( cd "$R/villa/spiral-fitting" && "$R/env/bin/python" -W ignore -c \
    "import torch, vc_spiral.surface_index, vc_spiral.spiral_sampling, fit_spiral; print('venv imports ok', torch.__version__, torch.version.cuda)" ) || fail "venv import test"
  printf 'route=venv\nmodules=%s\npython=%s\ndriver_min=525\n' "$MODS" "$R/env/bin/python" > "$R/route.txt"
  "$R/env/bin/python" -m pip freeze > "$R/FREEZE_venv.txt" 2>/dev/null || uv pip freeze --python "$R/env/bin/python" > "$R/FREEZE_venv.txt"
fi
say "route recorded: $(tr '\n' ' ' < "$R/route.txt")"
bash "$B/stage.sh" | tail -2
echo "SETUP OK"
