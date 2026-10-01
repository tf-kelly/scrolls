"""Stevens-bad share of SessJ's whole-scroll quilt trace and conflict areas (PREREG_bad_vs_flags.md, area figures).

SessJ's quilt.py is imported unchanged (collect_points, cell_stats, same defaults as the ARC build). The fitted surface is
not needed: TRACE and CONFLICT labels depend only on the patches. The run must reproduce the ARC totals (trace
648.325, conflict 17.506, all-patch conflict 32.595 cm²) before any split is reported.
Usage: PYTHONPATH=<dir holding vc_scale/> python quilt_membership.py DATASET WRAP_INDEX FLAGS BAD_IDS OUT_JSON
"""
import csv, json, sys, time
import numpy as np
from vc_scale import quilt as Q

DS, WI, FL, BAD, OUT = sys.argv[1:6]
CELL, PITCH_UM, FRAC, HAND = 4.0, 134.0, 0.6, 1          # quilt.py defaults, as scale_body.sh ran it
t0 = time.time()
axis = Q.load_axis(f"{DS}/umbilicus.json")
K = {str(r["patch"]): (int(float(r["k_q3c"])), float(r["thN"]), str(r["component"])) for r in csv.DictReader(open(WI))}
comp = max(set(v[2] for v in K.values()), key=lambda c: sum(1 for v in K.values() if v[2] == c))
flagged = set()
for r in csv.DictReader(open(FL)):
    flagged |= {str(r["patch_a"]), str(r["patch_b"])}
bad = set(open(BAD).read().split())
thr = FRAC * PITCH_UM / Q.VOX_UM
P, pid_of, geom, _ = Q.collect_points(DS, K, flagged, axis, HAND, comp, CELL)
isbad = np.zeros(len(pid_of), bool)
for i, p in pid_of.items():
    isbad[i] = p in bad
cm2 = (CELL * Q.VOX_UM * 1e-4) ** 2


def split(gc, gp, cells):
    """per cell in `cells` (sorted unique, subset of gc): any contributor bad, all contributors bad."""
    b = isbad[gp].astype(np.int64)
    u, st = np.unique(gc, return_index=True)
    nb = np.add.reduceat(b, st); n = np.diff(np.append(st, len(gc)))
    sel = np.isin(u, cells)
    return (nb[sel] > 0).sum(), (nb[sel] == n[sel]).sum()


T = dict(trace=0, trace_any_bad=0, trace_all_bad=0, conflict=0, conflict_pair_has_bad=0, conflict_any_bad=0,
         conflict_all=0, conflict_all_pair_has_bad=0, conflict_all_any_bad=0)
for w in sorted(P):
    d = P[w]; nth = geom[w][0]
    ith, iz = d["key"] % nth, d["key"] // nth
    cs, _, _, conf, pairs, g = Q.cell_stats(ith, iz, d["pid"], d["r"], nth, thr)
    T["conflict_all"] += int(conf.sum())
    T["conflict_all_pair_has_bad"] += int((isbad[pairs[:, 0]] | isbad[pairs[:, 1]]).sum()) if len(pairs) else 0
    T["conflict_all_any_bad"] += int(split(g[0], g[1], cs[conf])[0])
    keep = ~d["flag"]
    if not keep.any():
        continue
    cs, _, _, conf, pairs, g = Q.cell_stats(ith[keep], iz[keep], d["pid"][keep], d["r"][keep], nth, thr)
    T["trace"] += int((~conf).sum()); T["conflict"] += int(conf.sum())
    a, b = split(g[0], g[1], cs[~conf]); T["trace_any_bad"] += int(a); T["trace_all_bad"] += int(b)
    T["conflict_pair_has_bad"] += int((isbad[pairs[:, 0]] | isbad[pairs[:, 1]]).sum()) if len(pairs) else 0
    T["conflict_any_bad"] += int(split(g[0], g[1], cs[conf])[0])
A = {k: v * cm2 for k, v in T.items()}
ref = dict(trace=648.3246756950881, conflict=17.506033813408003, conflict_all=32.59497683120001)
out = dict(cells=T, cm2=A, reproduces_arc={k: abs(A[k] - v) < 1e-6 for k, v in ref.items()},
           indexed_bad_unflagged=int(sum(1 for p in bad if p in K and p not in flagged)),
           share=dict(trace_any_bad=A["trace_any_bad"] / A["trace"], trace_all_bad=A["trace_all_bad"] / A["trace"],
                      conflict_pair_has_bad=A["conflict_pair_has_bad"] / A["conflict"],
                      conflict_all_pair_has_bad=A["conflict_all_pair_has_bad"] / A["conflict_all"]),
           wall_s=round(time.time() - t0, 1))
json.dump(out, open(OUT, "w"), indent=1); print(json.dumps(out, indent=1))
