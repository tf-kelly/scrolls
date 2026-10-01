#!/usr/bin/env python3
"""F2 page 1 summary (F123_PROTOCOL.md + amendment): segment-check results on the patches under page 1's off-modal
area, against the registered criterion (clusters per cm2 above the Scroll 4 control's maximum, T1 control) and, post hoc,
against F1's 200 random placed Scroll 4 patches.
Usage: f2_summarise.py RUNS_JSONL LIST_JSON T1_CONTROL_JSON F1_RESULT_JSON OUT.json"""
import json, math, sys

import numpy as np


def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def main():
    rf, lf, cf, f1f, out = sys.argv[1:6]
    R = {}
    for l in open(rf): r = json.loads(l); R[r["patch"]] = r
    L = json.load(open(lf)); tot_nodes = sum(L["nodes"])
    sc = [r for r in R.values() if r["outcome"] != "error"]
    dens = np.array([r["clusters"] / r["area_cm2"] for r in sc]); nodes = np.array([r["off_nodes"] for r in sc])
    ctrl = [r["clusters"] / r["area_cm2"] for r in json.load(open(cf))["scroll4_control"]["runs"]]; cmax = max(ctrl)
    F1 = [r for r in json.load(open(f1f))["runs"] if r["outcome"] != "error"]; f1d = np.array([r["clusters"] / r["area_cm2"] for r in F1])
    k = sum(r["outcome"] == "pass" for r in sc); kf = sum(r["outcome"] == "pass" for r in F1)
    above = dens > cmax
    res = dict(patches_listed=len(L["patches"]), patches_run=len(R), scored=len(sc), errors=len(R) - len(sc),
               off_modal_area_covered_share=round(float(nodes.sum() / tot_nodes), 4),
               power_values=sorted({r["power"] for r in sc}), clean_tests=sum((r["power"] or 0) >= 0.5 for r in sc),
               pass_rate=round(k / len(sc), 4), pass_wilson95=wilson(k, len(sc)),
               clusters_per_cm2_median=round(float(np.median(dens)), 1),
               registered=dict(control_max_clusters_per_cm2=round(cmax, 1), share_above=round(float(above.mean()), 4),
                               area_weighted_share_above=round(float(nodes[above].sum() / nodes.sum()), 4),
                               more_than_half=bool(above.mean() > 0.5)),
               posthoc_vs_F1=dict(F1_pass_rate=round(kf / len(F1), 4), F1_pass_wilson95=wilson(kf, len(F1)),
                                  F1_clusters_per_cm2_median=round(float(np.median(f1d)), 1),
                                  share_above_F1_p90=round(float((dens > np.percentile(f1d, 90)).mean()), 4),
                                  F1_p90=round(float(np.percentile(f1d, 90)), 1)))
    json.dump(dict(protocol="F123_PROTOCOL.md F2 (+ amendment)", summary=res), open(out, "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
