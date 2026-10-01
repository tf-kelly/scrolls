#!/usr/bin/env bash
# How the shipped villa_spiral.sif was built in the Claude container (no download.pytorch.org, no GitHub releases, and
# singularity %post cannot run: CAP_SYS_RESOURCE is missing). Route: pull a sandbox, install with plain chroot, pack.
# Deviation from villa's lock: torch 2.11.0 from PyPI (CUDA 13.0 build + its nvidia-*-cu13 deps) instead of
# 2.11.0+cu128; every other package pinned to villa's uv.lock (uv export --frozen). pandas added (evaluation only).
# Usage: bash build_sif_here.sh VILLA_GIT_DIR WORKDIR     (VILLA_GIT_DIR at f4570bf; output WORKDIR/villa_spiral.sif)
set -euo pipefail
VILLA=$1; W=$2; SBX=$W/sbx; mkdir -p "$W"
[ "$(git -C "$VILLA" rev-parse HEAD)" = f4570bfa6c2b357fd24a17b46f8a43becf87ea8d ] || { echo "villa not at f4570bf"; exit 1; }
git -C "$VILLA" diff --quiet -- spiral-fitting/uv.lock || { echo "uv.lock modified"; exit 1; }
rm -rf "$SBX"; singularity build --sandbox "$SBX" docker://python:3.14-bookworm
mkdir -p "$SBX/opt/villa"
git -C "$VILLA" archive f4570bfa6c2b357fd24a17b46f8a43becf87ea8d spiral-fitting vesuvius/src/vc3d_fiber_format | tar -x -C "$SBX/opt/villa"
(cd "$VILLA/spiral-fitting" && uv export --frozen --no-hashes --no-emit-project --no-header) \
  | grep -v -E '^(torch==|triton==|nvidia-|cuda-bindings|cuda-pathfinder|cuda-toolkit|triton-windows)' > "$SBX/tmp/req_pinned.txt"
cp /etc/resolv.conf "$SBX/etc/resolv.conf"; cp "${SSL_CERT_FILE:-/root/.ccr/ca-bundle.crt}" "$SBX/tmp/proxy-ca.crt"
mount -t proc proc "$SBX/proc"; mount --bind /dev "$SBX/dev"; trap 'umount "$SBX/proc" "$SBX/dev" 2>/dev/null || true' EXIT
# pip, not uv: uv cannot discover interpreters inside this bare chroot. Same pins (exported from villa's uv.lock).
chroot "$SBX" /usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/root HTTPS_PROXY="${HTTPS_PROXY:-}" HTTP_PROXY="${HTTP_PROXY:-}" \
  SSL_CERT_FILE=/tmp/proxy-ca.crt PIP_CERT=/tmp/proxy-ca.crt PIP_NO_CACHE_DIR=1 PIP_ROOT_USER_ACTION=ignore /bin/bash -euo pipefail -c '
    python3.14 -m venv /opt/venv
    /opt/venv/bin/pip install -q --upgrade pip
    /opt/venv/bin/pip install -q -r /tmp/req_pinned.txt
    /opt/venv/bin/pip install -q torch==2.11.0 pandas
    /opt/venv/bin/pip install -q --no-deps /opt/villa/spiral-fitting
    # villa runs from its own directory, where the source vc_spiral/ (Python only) shadows site-packages: copy the
    # compiled nanobind modules next to it (what the editable install achieves on a workstation).
    cp /opt/venv/lib/python3.14/site-packages/vc_spiral/*.so /opt/villa/spiral-fitting/vc_spiral/
    cd /opt/villa/spiral-fitting && /opt/venv/bin/python -c "import torch, vc_spiral.surface_index, vc_spiral.spiral_sampling, fit_spiral; print(\"import ok\", torch.__version__, torch.version.cuda)"
    /opt/venv/bin/pip freeze > /opt/FREEZE.txt
    rm -rf /root/.cache'
umount "$SBX/proc" "$SBX/dev"; trap - EXIT
# never ship the build host's proxy CA or resolver
rm -f "$SBX/tmp/proxy-ca.crt" "$SBX/tmp/req_pinned.txt"; : > "$SBX/etc/resolv.conf"
mkdir -p "$SBX/.singularity.d/env"
printf '%s\n' 'export PATH=/opt/venv/bin:$PATH' 'export PYTHONNOUSERSITE=1' 'export WANDB_MODE=disabled' > "$SBX/.singularity.d/env/90-villa.sh"
echo f4570bfa6c2b357fd24a17b46f8a43becf87ea8d > "$SBX/opt/VILLA_COMMIT"
singularity build --force "$W/villa_spiral.sif" "$SBX"
sha256sum "$W/villa_spiral.sif"; ls -la "$W/villa_spiral.sif"
