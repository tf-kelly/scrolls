#!/bin/bash
# SessB-3 input check (login node; also run at the end of setup.sh). Every file in INPUTS.sha256 (paths relative to
# $DATA/vc_arc) must be present with the right sha256. villa.sif is checked only on the apptainer route.
# PENDING lines (SessA-12's whole-scroll files, not yet produced) block arm_a/arm_b but not test_job.sh.
set -uo pipefail
R=${VC_ARC_ROOT:-$DATA/vc_arc}; cd "$R" || exit 1
ROUTE=$(awk -F= '$1=="route"{print $2}' route.txt 2>/dev/null); ok=0; bad=0; pend=0
while read -r h f _; do
  [ -z "${h:-}" ] || [ "${h:0:1}" = "#" ] && continue
  if [ "$h" = PENDING ]; then echo "PENDING  $f"; pend=$((pend+1)); continue; fi
  [ "$f" = villa.sif ] && [ "$ROUTE" != apptainer ] && continue
  if [ ! -f "$f" ]; then echo "MISSING  $f"; bad=$((bad+1)); continue; fi
  if [ "$(sha256sum "$f" | cut -d' ' -f1)" = "$h" ]; then ok=$((ok+1)); else echo "BAD-SHA  $f"; bad=$((bad+1)); fi
done < bundle/INPUTS.sha256
echo "inputs ok=$ok bad=$bad pending=$pend   route=${ROUTE:-not set (run setup.sh)}"
if [ $bad -gt 0 ]; then echo "STAGE FAIL: fix the files listed above"; exit 1; fi
if [ $pend -gt 0 ]; then echo "READY FOR test_job.sh ONLY (arm_a/arm_b wait for the PENDING whole-scroll files)"; exit 0; fi
echo "ALL $ok INPUTS OK: ready for test_job.sh, arm_a.sh, arm_b.sh"
