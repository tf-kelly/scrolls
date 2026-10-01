#!/usr/bin/env bash
# Build VC3D at the pinned villa commit with Tools -> Sheet check applied.
# Usage: build_vc3d.sh VILLA_DIR [--apt]
#   VILLA_DIR  a checkout of ScrollPrize/villa (cloned if missing).
#   --apt      install build dependencies first (Ubuntu 24.04, root).
set -euo pipefail
PIN=f4570bfa6c2b357fd24a17b46f8a43becf87ea8d   # villa main, 2026-09-26, "Spiral orientation (#1899)"
HERE=$(cd "$(dirname "$0")" && pwd); VILLA=$1
if [ "${2:-}" = --apt ]; then
  # Upstream's list (volume-cartographer/scripts/install_build_deps.sh) minus flang/scotch
  # (flatboi is disabled below) and the AWS CLI; plus Xvfb tools for the in-app test.
  apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential git cmake ninja-build pkg-config qt6-base-dev \
    libboost-system-dev libboost-program-options-dev libceres-dev libsuitesparse-dev \
    libopencv-dev libopencv-contrib-dev libcgal-dev libmpfr-dev libgmp-dev \
    libblosc-dev libzstd-dev libcurl4-openssl-dev nlohmann-json3-dev libavahi-client-dev \
    liblz4-dev libtiff-dev zlib1g-dev libopenblas-dev liblapack-dev liblapacke-dev libomp-dev libhwloc-dev \
    xvfb xauth xdotool imagemagick libxkbcommon-x11-0 libxcb-cursor0 libgl1-mesa-dri
fi
git -C "$VILLA" rev-parse --git-dir >/dev/null 2>&1 || git clone --filter=blob:none https://github.com/ScrollPrize/villa.git "$VILLA"
cd "$VILLA"
git checkout -q "$PIN"
if git apply --check "$HERE/villa_sheet_check.patch" 2>/dev/null; then
  git apply "$HERE/villa_sheet_check.patch"
elif git apply --reverse --check "$HERE/villa_sheet_check.patch" 2>/dev/null; then
  echo "patch already applied at $PIN; continuing"
else
  echo "ERROR: villa_sheet_check.patch does not apply to villa at $PIN (and is not already applied)" >&2
  exit 1
fi
cd volume-cartographer
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DVC_BUILD_FLATBOI=OFF -DVC_TESTING=OFF -DVC_BUILD_PYTHON=OFF
ninja -C build -j"$(nproc)" VC3D
echo "built $(pwd)/build/bin/VC3D"
