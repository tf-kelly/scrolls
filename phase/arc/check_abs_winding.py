#!/usr/bin/env python3
"""Validate an abs_winding.json (villa point-collections v1, role 'absolute') and print one summary line.
Exit 1 on any problem. Usage: check_abs_winding.py abs_winding.json"""
import json, math, sys
p = sys.argv[1]; d = json.load(open(p))
assert d.get("vc_pointcollections_json_version") == "1", "version must be '1'"
cols = d.get("collections", {}); assert cols, "no collections"
n = 0; lo = math.inf; hi = -math.inf
for cid, c in cols.items():
    int(cid); assert "name" in c and "points" in c, f"collection {cid} needs name+points"
    for pid, pt in c["points"].items():
        int(pid); q = pt["p"]; assert len(q) == 3 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in q), f"bad p in {cid}/{pid}"
        w = pt.get("wind_a"); assert w is not None and math.isfinite(w) and w > 0, f"wind_a must be finite and > 0 in {cid}/{pid}"
        n += 1; lo = min(lo, w); hi = max(hi, w)
print(f"{n} points in {len(cols)} collections, wind_a in [{lo:g}, {hi:g}]")
