"""pipeline9-filter: reference-free wrap numbering and majority-turn pruning for W. Stevens' pipeline9 outputs.

  pipeline9-filter hybrid --rel rel.csv --badpatches badpatches_b.csv --patch-table patches.csv --out DIR
  pipeline9-filter risk   --rel rel.csv --switch-risk switch_risk.csv --out DIR     (contract §4.6)
  pipeline9-filter slab2  --out DIR      (P1e's combined row on the committed slab-2 inputs)
  pipeline9-filter fixture --out DIR     (the same rule on phase/data_small/fixture)
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


def _repo(arg):
    if arg:
        return Path(arg).resolve()
    for p in Path(__file__).resolve().parents:
        if (p / "phase/tools/CONTRACT.md").exists():
            return p
    raise SystemExit("cannot find the repository; pass --repo")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline9-filter", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo")
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hybrid", help="(iii-rf) cuts + pipeline9 deletions + majority-turn pruning; pipeline9 formats out")
    h.add_argument("--rel", required=True); h.add_argument("--badpatches", required=True)
    g = h.add_mutually_exclusive_group(required=True)
    g.add_argument("--patch-table", help="phase/x1/patches.csv-style table (id, n, bbox, centroid)")
    g.add_argument("--patches", nargs="+", help="pipeline9 patches: zip(s)/dir(s) of tifxyz patch_N/ or N.bin; the table is derived")
    h.add_argument("--wrap-index"); h.add_argument("--flip1"); h.add_argument("--edges"); h.add_argument("--k-ref")
    h.add_argument("--x6-pairs"); h.add_argument("--patches-subset", help="file of patch ids to restrict to (one per line)")
    h.add_argument("--page-min-mm2", type=float, default=100.0); h.add_argument("--bootstrap", action="store_true")
    h.add_argument("--restrict-bad", action="store_true", help="write only flagged ids that occur in rel.csv")
    h.add_argument("--no-rf", action="store_true", help="skip the (iii-rf) wrap-index cuts: pipeline9 deletions + pruning only")
    h.add_argument("--out", required=True)
    r = sub.add_parser("risk", help="contract §4.6: remove joins flagged by the frozen risk model")
    r.add_argument("--rel", required=True); r.add_argument("--switch-risk", required=True, help="patch_a, patch_b, risk, flagged[, sep_um]")
    r.add_argument("--out", required=True)
    for name in ("slab2", "fixture"):
        s = sub.add_parser(name); s.add_argument("--out", required=True); s.add_argument("--bootstrap", action="store_true")
        s.add_argument("--no-rf", action="store_true")
        s.add_argument("--wrap-index", help="override the committed p1b_q3c_k.csv (e.g. a SessA-15 tie-broken index)")
    a = ap.parse_args(argv)
    repo = _repo(a.repo)
    from . import core
    if a.cmd == "risk":
        sys.path.insert(0, str(repo / "phase/tools/vc_sheet_check"))
        from vc_sheet_check import p9filter
        rows = list(csv.DictReader(open(a.switch_risk)))
        thr = 0.3293271860685008
        git = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo).stdout.strip()
        res = p9filter.filter_rel(a.rel, a.out, rows, thr, dict(contract="v1", git=git))
        print(json.dumps(res, indent=1)); return 0
    if a.cmd in ("slab2", "fixture"):
        F = repo / "phase/data_small/fixture"
        base = dict(patches=None, wrap_index=a.wrap_index or str(repo / "phase/p1page/p1b_q3c_k.csv"), flip1=str(repo / "phase/x10/flip1_pairs.csv"),
                    edges=str(repo / "phase/x10/x7_v7_edges.csv"), k_ref=None, restrict_bad=False, patches_subset=None,
                    bootstrap=a.bootstrap, no_rf=a.no_rf, out=a.out)
        if a.cmd == "slab2":
            a = argparse.Namespace(rel=str(repo / "phase/x5/rel.csv"), badpatches=str(repo / "phase/x5/badpatches_b.csv"),
                                   patch_table=str(repo / "phase/x1/patches.csv"), x6_pairs=str(repo / "phase/x6/x6b_pairs.csv"),
                                   page_min_mm2=100.0, **base)
        else:
            a = argparse.Namespace(rel=str(F / "rel.csv"), badpatches=str(F / "pipeline9_badpatches_b.csv"),
                                   patch_table=str(F / "patches.csv"), x6_pairs=str(F / "x6_pairs.csv"),
                                   page_min_mm2=json.load(open(F / "golden/pages_metrics.json"))["iii_rf"]["page_min_mm2"], **base)
    if getattr(a, "patches", None):
        a.patch_table = core.table_from_patches(a.patches, Path(a.out), repo)
    a.wrap_index = a.wrap_index or str(repo / "phase/p1page/p1b_q3c_k.csv")
    a.flip1 = a.flip1 or str(repo / "phase/x10/flip1_pairs.csv")
    a.edges = a.edges or str(repo / "phase/x10/x7_v7_edges.csv")
    res = core.run(a, repo)
    print(json.dumps(res, indent=1, default=float)); return 0


if __name__ == "__main__":
    sys.exit(main())
