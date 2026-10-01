#!/bin/bash
# Make run_arm.sh accept an absolute-winding file (ABS_WINDING=/path/abs_winding.json from the wrapper): copies it into the
# staged dataset and turns on villa's input_use_pcl_absolute. Idempotent. Run once on the login node (edits one file).
set -euo pipefail
F="${DATA:?}/vc_arc/bundle/run_arm.sh"
if grep -q 'ABS_WINDING' "$F"; then echo "ALREADY PATCHED"; else
python3 - "$F" <<'PY'
import sys; p=sys.argv[1]; s=open(p).read()
old1='[ -n "${ROLES:-}" ] || rm -f "$W/ds/same_windings.json" "$W/ds/relative_windings.json"\n'
new1=old1+'''if [ -n "${ABS_WINDING:-}" ]; then   # arm c: absolute windings from the index (villa role "absolute", by file name)
  cp "$ABS_WINDING" "$W/ds/abs_winding.json" || { say "FAIL: copy $ABS_WINDING"; exit 2; }
  ABSUM=$(python3 "$B/check_abs_winding.py" "$W/ds/abs_winding.json") || { say "FAIL: abs_winding.json check"; exit 2; }
  say "abs windings: $ABSUM"
else rm -f "$W/ds/abs_winding.json"; fi
'''
old2='SessG=false; SAME=false; [ -n "${ROLES:-}" ] && { SessG=true; SAME=true; }\n'
new2=old2+'ABS=false; [ -n "${ABS_WINDING:-}" ] && ABS=true\n'
old3='\\"input_use_pcl_absolute\\":false'
new3='\\"input_use_pcl_absolute\\":$ABS'
for o in (old1,old2,old3): assert s.count(o)==1, "expected text not found: "+o[:40]
s=s.replace(old1,new1).replace(old2,new2).replace(old3,new3)
open(p,'w').write(s); print("PATCH APPLIED")
PY
fi
bash -n "$F" && echo "SYNTAX OK"
