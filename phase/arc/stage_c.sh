#!/bin/bash
# Scroll 4 arm (c) tranche check: tranche_s4_abs = tranche_s4_whole's dataset.tgz (linked) + abs_winding.json + params.env.
# Light (no unpack): fine on the login node. Last line: "TRANCHE OK" or "TRANCHE FAILED: <reason>".
set -uo pipefail
R=${VC_ARC_ROOT:-$DATA/vc_arc}; T=$R/tranche_s4_abs; S=$R/tranche_s4_whole; B=$R/bundle
fail() { echo "TRANCHE FAILED: $*"; rm -f "$T/READY"; exit 1; }
[ -f "$S/READY" ] || fail "tranche_s4_whole is not staged ($S/READY missing)"
[ -f "$T/abs_winding.json" ] || fail "copy abs_winding.json, params.env and TRANCHE.sha256 into $T first"
[ -f "$T/TRANCHE.sha256" ] || fail "TRANCHE.sha256 missing in $T"
[ -f "$T/params.env" ] || cp "$S/params.env" "$T/params.env"
ln -sfn "$S/dataset.tgz" "$T/dataset.tgz"
( cd "$T" && sha256sum -c --quiet TRANCHE.sha256 ) || fail "sha256 mismatch (see above)"
grep -q ABS_WINDING "$B/run_arm.sh" || fail "run bundle/patch_abs.sh first"
PY=$(awk -F= '$1=="python"{print $2}' "$R/route.txt"); [ -n "$PY" ] || PY=python3
SUM=$("$PY" "$B/check_abs_winding.py" "$T/abs_winding.json") || fail "abs_winding.json invalid"
source "$T/params.env"; echo "NUM_WINDINGS=$NUM_WINDINGS Z0=$Z0 Z1=$Z1 abs: $SUM"
echo "Z0=$Z0 Z1=$Z1 STEPS=${STEPS:-30000} abs=$(sha256sum "$T/abs_winding.json" | cut -c1-16) $(date -u +%FT%TZ)" > "$T/READY"
echo "TRANCHE OK"
