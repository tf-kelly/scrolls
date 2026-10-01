#!/usr/bin/env python3
"""Fixture v1.1 (additive; v1 files are unchanged): golden §4.1 clusters for region A.

  golden/expected_cross_turn_clusters.json  X6-confirmed cross-turn joins: rel.csv joins (minus flip1) whose X6 truth
                                            is 'adjacent' and which have an evaluated-point midpoint inside region A,
                                            clustered by §4.1's rule (single linkage at 50 µm on their evaluated points).
                                            This is the reference side (X6 labels), not detector output.
  golden/report.json                        example_outputs.py's report for region A (detector side: switch-score flags
                                            and wrong-turn points), with the git field blanked.
Coordinates are zyx scan voxels (Amendment 4 §A4.4)."""
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

F = Path(__file__).resolve().parent; R = F.parents[2]
sys.path.insert(0, str(R / "phase/tools")); sys.path.insert(0, str(R / "phase/h1"))
import contract_io as CIO  # noqa: E402
import metrics as M  # noqa: E402
from refmesh import ang, build_axis  # noqa: E402


def expected_clusters():
    prov = json.load(open(F / "provenance.json")); reg = prov["regions"]["A_rich"]
    flip1 = {M.jkey(*r[:2]) for r in csv.reader(open(R / "phase/x10/flip1_pairs.csv"))}
    joins = {M.jkey(*r[:2]) for r in csv.reader(open(F / "rel.csv"))} - flip1
    rows = list(csv.DictReader(open(F / "x6_pairs.csv"))); P = np.load(F / "x6_points.npz")
    sep = {M.jkey(r["patch_a"], r["patch_b"]): float(r["sep_um"]) for r in rows}
    pts = {}
    for i, r in enumerate(rows):
        k = M.jkey(r["patch_a"], r["patch_b"])
        if r["truth"] != "adjacent" or k not in joins:
            continue
        m = P["pair"] == i; mid = (P["PA"][m] + P["PB"][m]) / 2
        inb = np.all([(mid[:, j] >= reg[a][0]) & (mid[:, j] < reg[a][1]) for j, a in ((0, "x"), (1, "y"), (2, "z"))], axis=0)
        if inb.any():
            pts[k] = np.concatenate([P["PA"][m], P["PB"][m], mid]).astype(np.float64)   # evaluated points = PA, PB and midpoint (§4.2)
    x6all = list(csv.DictReader(open(R / "phase/x6/x6b_pairs.csv")))
    axis_xy, _ = build_axis(sorted({r["patch_a"] for r in x6all} | {r["patch_b"] for r in x6all}, key=int), None)
    wrap = {int(r["patch"]): int(r["wrap_index"]) for r in csv.DictReader(open(F / "golden/wrap_index.csv"))}
    area = M.bbox_area_mm2(F / "patches.csv")
    risk = {M.jkey(r["patch_a"], r["patch_b"]): float(r["risk"]) for r in csv.DictReader(open(F / "golden/switch_risk.csv"))}
    out = []
    for g in CIO.single_linkage(pts):
        pat = sorted({p for k in g for p in k})
        c = CIO.cluster_record(len(out), "x6_cross_turn", np.concatenate([pts[k] for k in g]), pat, g, lambda x: ang(x, axis_xy), wrap,
                               sum(area[p] for p in pat) / 100, max(risk.get(k, float("nan")) for k in g))
        c["contact_pairs"] = sum(sep[k] < 50 for k in g); c["pairs_flagged_by_switch_score"] = sum(risk.get(k, 0.0) >= 0.3293271860685008 for k in g)
        c["pairs_without_switch_score"] = sum(k not in risk for k in g)
        out.append(c)
    return dict(definition=__doc__.split("\n\n")[0], region="A_rich", n_joins=len(pts), clusters=out)


if __name__ == "__main__":
    e = expected_clusters(); json.dump(e, open(F / "golden/expected_cross_turn_clusters.json", "w"), indent=1)
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, str(R / "phase/tools/example_outputs.py"), d], check=True, capture_output=True)
        rep = json.load(open(Path(d) / "report.json")); rep["git"] = "(blanked in golden)"
        json.dump(rep, open(F / "golden/report.json", "w"), indent=1)
    print(e["n_joins"], "joins,", len(e["clusters"]), "expected clusters;", len(rep["clusters"]), "report clusters")
    for c in e["clusters"]:
        print(c["id"], c["n_pairs"], c["centroid_zyx"], c["contact_pairs"], c["pairs_flagged_by_switch_score"])
