#!/bin/bash
# Scroll 4 redo tranche check: tranche_s4_cap = tranche_s4_whole's dataset.tgz (linked) + its own params.env (cap 80, initial dr 32).
# Light; login node is fine. Last line "TRANCHE OK" or "TRANCHE FAILED: <reason>".
set -uo pipefail
R=${VC_ARC_ROOT:-$DATA/vc_arc}; T=$R/tranche_s4_cap; S=$R/tranche_s4_whole; B=$R/bundle
fail() { echo "TRANCHE FAILED: $*"; rm -f "$T/READY"; exit 1; }
[ -f "$S/READY" ] || fail "tranche_s4_whole is not staged ($S/READY missing)"
[ -f "$T/params.env" ] && [ -f "$T/TRANCHE.sha256" ] || fail "params.env / TRANCHE.sha256 missing in $T (they ship in the add-on)"
ln -sfn "$S/dataset.tgz" "$T/dataset.tgz"
( cd "$T" && sha256sum -c --quiet TRANCHE.sha256 ) || fail "sha256 mismatch"
grep -q INIT_DR "$B/run_arm.sh" || fail "run bundle/patch_initdr.sh first"
source "$T/params.env"; echo "NUM_WINDINGS=$NUM_WINDINGS INIT_DR=$INIT_DR Z0=$Z0 Z1=$Z1"
echo "Z0=$Z0 Z1=$Z1 STEPS=${STEPS:-30000} cap=$NUM_WINDINGS initdr=$INIT_DR $(date -u +%FT%TZ)" > "$T/READY"
echo "TRANCHE OK"
