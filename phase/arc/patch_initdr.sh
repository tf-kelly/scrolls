#!/bin/bash
# Make run_arm.sh pass villa's model_initial_dr_per_winding (INIT_DR from the wrapper; villa default 16.0). Idempotent; login node.
set -euo pipefail
F="${DATA:?}/vc_arc/bundle/run_arm.sh"
if grep -q 'INIT_DR' "$F"; then echo "ALREADY PATCHED"; else
python3 - "$F" <<'PY'
import sys; p=sys.argv[1]; s=open(p).read()
old='\\"model_gap_expander_num_windings\\":$NUM_WINDINGS,'
new='\\"model_gap_expander_num_windings\\":$NUM_WINDINGS,\\"model_initial_dr_per_winding\\":${INIT_DR:-16.0},'
assert s.count(old)==1, "expected CFG text not found"
old2='say "gap capacity=$CAP"'
new2='say "gap capacity=$CAP initial_dr_per_winding=${INIT_DR:-16.0}"'
assert s.count(old2)==1
open(p,'w').write(s.replace(old,new).replace(old2,new2)); print("PATCH APPLIED")
PY
fi
bash -n "$F" && echo "SYNTAX OK"
