#!/usr/bin/env python3
"""SessA instruction (a): page-1 boundary diagnosis, exploratory (not registered; request due 22:15 London).
Joins across the boundary from P1FIX step 2 (page1_crossing.json), and what the boundary is made of on the page grid:
key changes between 4-neighbour page nodes, split by same patch / different patch and by page-unwrap residual jumps.
Usage: p1diag_boundary.py PAGE1_KEY_NPZ PAGE1_CROSSING_JSON OUT.json"""
import collections as C, json, sys

import numpy as np


def joins(R):
    kind = lambda r: "M-m" if {r["side_a"], r["side_b"]} == {"M", "m"} else "+".join(sorted((r["side_a"], r["side_b"])))
    out = {"by_kind": dict(C.Counter(kind(r) for r in R))}
    for kd in sorted(out["by_kind"]):
        S = [r for r in R if kind(r) == kd]
        o = dict(n=len(S), verdict=dict(C.Counter(r["verdict"] for r in S)), d_i=dict(C.Counter(str(r["d_i"]) for r in S)),
                 with_unsatisfied_terms=sum(bool(r["unsatisfied_terms"]) for r in S), below_threshold=sum(r["below_threshold"] for r in S))
        if kd == "M-m":
            o["dk_M_to_m"] = dict(C.Counter(str((r["k_b"] - r["k_a"]) if r["side_a"] == "M" else (r["k_a"] - r["k_b"])) for r in S))
            o["joins"] = [dict(M=r["a"] if r["side_a"] == "M" else r["b"], m=r["b"] if r["side_a"] == "M" else r["a"],
                               k_M=r["k_a"] if r["side_a"] == "M" else r["k_b"], k_m=r["k_b"] if r["side_a"] == "M" else r["k_a"],
                               d_i=r["d_i"], verdict=r["verdict"], agreement=r["agreement"], unsatisfied=r["unsatisfied_terms"]) for r in S]
        else:
            o["dk"] = dict(C.Counter(str(abs(r["k_b"] - r["k_a"])) for r in S))
        out[kd] = o
    return out


def grid(K):
    ii, jj, pid, key, Th, onm, ok = (K[k] for k in ("ii", "jj", "patch", "key", "theta_unwrapped", "on_modal", "matched"))
    H, W = ii.max() + 1, jj.max() + 1; idx = -np.ones((H, W), np.int64); idx[ii, jj] = np.arange(len(ii)); t = C.Counter()
    for di, dj in ((0, 1), (1, 0)):
        i2, j2 = ii + di, jj + dj; m = (i2 < H) & (j2 < W); a = np.where(m)[0]; b = idx[i2[m], j2[m]]
        g = b >= 0; a, b = a[g], b[g]; g = ok[a] & ok[b]; a, b = a[g], b[g]
        jump = np.abs(Th[a] - Th[b]) > np.pi; bd = onm[a] != onm[b]; kd = key[a] != key[b]; same = pid[a] == pid[b]
        t["edges"] += len(a); t["unwrap_jump_edges"] += int(jump.sum())
        t["key_change_edges"] += int(kd.sum()); t["key_change_same_patch"] += int((kd & same).sum())
        t["key_change_at_unwrap_jump"] += int((kd & jump).sum())
        t["boundary_edges"] += int(bd.sum()); t["boundary_same_patch"] += int((bd & same).sum()); t["boundary_at_unwrap_jump"] += int((bd & jump).sum())
    t = dict(t)
    t["unwrap_jump_share_of_all_edges"] = round(t["unwrap_jump_edges"] / t["edges"], 5)
    t["boundary_at_unwrap_jump_share"] = round(t["boundary_at_unwrap_jump"] / t["boundary_edges"], 4)
    t["boundary_same_patch_share"] = round(t["boundary_same_patch"] / t["boundary_edges"], 4)
    return t


def main():
    kf, cf, out = sys.argv[1:4]
    res = dict(note="exploratory; boundary = smoothed on/off-modal flag change between 4-neighbour page nodes (16 vox)",
               joins=joins(json.load(open(cf))["constraints"]), grid=grid(np.load(kf)))
    json.dump(res, open(out, "w"), indent=1); print(json.dumps({k: v for k, v in res["joins"].items() if k != "M-m"}, indent=1))
    print(json.dumps({k: v for k, v in res["joins"]["M-m"].items() if k != "joins"}, indent=1)); print(json.dumps(res["grid"], indent=1))


if __name__ == "__main__":
    main()
