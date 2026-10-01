"""pipeline9 filter: our reference-free wrap numbering and majority-turn pruning applied to W. Stevens'
pipeline9 outputs, written back in pipeline9's own formats.

pipeline9 formats read and written (P9, phase/x5/ and fixture/):
  rel.csv            aligner output, no header: patch_a, patch_b, flip, then affine terms. Kept rows are copied as
                     raw bytes (byte-identical).
  badpatches_b.csv   mode-b flagged patches, one id per line (pipeline9's own exclusion list).
  badpatchscores_b.csv  patch2, patch1, maxDistance (read only, for the §4.6 table).
  patches            tifxyz patch_N/ folders or .bin quadmeshes (zip or directory); used only for ids, bboxes and
                     areas -- pipeline9's assembly excludes patches through badpatches_b.csv, so patch files are not
                     rewritten.

The hybrid ("combined") row of P1e (phase/notes/C1.md on x10, P1e (1); phase/p1page/p1e_frontier.py):
  1. joins U = rel.csv pairs minus flip=1-only pairs;
  2. (iii-rf) cuts: keep a join iff an end has no wrap index, or its cut-adjusted wrap difference is 0 and the direct
     measurement (d_i else d_ii) is absent or 0 (p1b_rf_joins.py);
  3. pipeline9 deletions: drop every join touching a mode-b flagged patch;
  4. majority-turn pruning by our continuous turn t_q = k + theta/2pi (p1d_prune.prune, vendored unmodified) on the
     pages (components >= page_min) of the result; drop the minority patches and their joins.
Pages and M1/M2/M3 come from phase/tools/metrics.py (contract §5).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

TWO_PI = 2 * np.pi


def jkey(a, b):
    a, b = int(a), int(b)
    return (a, b) if a < b else (b, a)


def cross(t1, t2):
    e = t1 + (np.mod(t2 - t1 + np.pi, TWO_PI) - np.pi)
    return 1 if e >= TWO_PI else (-1 if e < 0 else 0)


# ------------------------------------------------------------------------------------------------ formats

def read_rel_pairs(path):
    out = []
    for row in csv.reader(open(path)):
        try:
            out.append(jkey(row[0], row[1]))
        except (ValueError, IndexError):
            continue
    return out


def read_ids(path):
    return {int(x) for x in open(path).read().split() if x.strip().lstrip("-").isdigit()} if path else set()


def read_wrap(path):
    """p1b_q3c_k.csv: patch, k_q3c, component, thN -> {patch: (k, theta)}; handedness from the sibling .json."""
    K = {int(r["patch"]): (int(r["k_q3c"]), float(r["thN"])) for r in csv.DictReader(open(path))}
    j = Path(path).with_suffix(".json")
    s = json.load(open(j))["s_chosen"] if j.exists() else 1
    return K, s


def read_direct(path):
    out = {}
    if path and Path(path).exists():
        for r in csv.DictReader(open(path)):
            for c in ("d_i", "d_ii"):
                x = r.get(c)
                if x not in (None, "", "None"):
                    out[jkey(r["patch_a"], r["patch_b"])] = int(float(x)); break
    return out


def write_rel(src, dst, keep):
    """Copy rel.csv rows whose unordered pair is in `keep`, byte for byte."""
    n = 0
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        for line in fi:
            p = line.decode("utf-8", "replace").split(",")
            try:
                k = jkey(p[0], p[1])
            except (ValueError, IndexError):
                continue
            if k in keep:
                fo.write(line); n += 1
    return n


def table_from_patches(paths, out, repo):
    """Read pipeline9 patches (tifxyz patch_N/ folders or .bin quadmeshes, zip or directory) with the vendored
    switchwitness reader and write a phase/x1/patches.csv-style table (bbox and centroid in x, y, z)."""
    sys.path.insert(0, str(Path(repo) / "phase/tools/vc_sheet_check"))
    from vc_sheet_check import sources
    G, _ = sources.load_patches(paths)
    rows = sources.patch_table(G)
    Path(out).mkdir(parents=True, exist_ok=True)
    p = Path(out) / "patches_table.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    return str(p)


def write_ids(path, ids):
    with open(path, "w") as f:
        for i in sorted(ids):
            f.write(f"{i}\n")


# ------------------------------------------------------------------------------------------------ method

def rf_joins(U, K, s, direct):
    kept, cut = [], []
    for a, b in U:
        if a in K and b in K:
            dk = K[b][0] - K[a][0] - s * cross(K[a][1], K[b][1])
            d = direct.get((a, b))
            ok = dk == 0 and (d is None or d == 0)
        else:
            ok = True
        (kept if ok else cut).append((a, b))
    return kept, cut


def _vendor():
    here = Path(__file__).resolve().parent / "_vendor"
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    import p1d_prune  # noqa: E402  (vendored unmodified)
    return p1d_prune


def hybrid(U, K, s, direct, bad, area, nodes, page_min_mm2, pages_fn, use_rf=True):
    """The combined row's join set. Returns dict with the join sets at each step and the pruned patches.
    use_rf=False skips the (iii-rf) cuts: pipeline9 deletions + pruning only (P1d's "(ii) + pruning" row)."""
    PD = _vendor()
    rf, cut = rf_joins(U, K, s, direct) if use_rf else (list(U), [])
    E1 = [k for k in rf if k[0] not in bad and k[1] not in bad]
    tq = {p: K[p][0] + (K[p][1] % TWO_PI) / TWO_PI for p in K}
    drop = PD.prune(pages_fn(E1, nodes), E1, area, tq)
    E = [k for k in E1 if k[0] not in drop and k[1] not in drop]
    return dict(rf=rf, rf_cut=cut, after_p9=E1, joins=E, pruned=drop, nodes_after=[p for p in nodes if p not in drop])


def run(args, repo):
    sys.path.insert(0, str(Path(repo) / "phase/tools"))
    import metrics as M
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    flip1 = set(read_rel_pairs(args.flip1)) if args.flip1 else set()
    U_all = read_rel_pairs(args.rel)
    U = sorted(set(U_all) - flip1)
    K, s = read_wrap(args.wrap_index)
    direct = read_direct(args.edges)
    bad = read_ids(args.badpatches)
    area = M.bbox_area_mm2(args.patch_table)
    nodes = sorted({p for k in U for p in k})
    if args.patches_subset:
        keep_ids = read_ids(args.patches_subset)
        U = [k for k in U if k[0] in keep_ids and k[1] in keep_ids]; nodes = [p for p in nodes if p in keep_ids]
    pages_fn = lambda E, nd: M.pages(E, nd, area, args.page_min_mm2)
    H = hybrid(U, K, s, direct, bad, area, nodes, args.page_min_mm2, pages_fn, use_rf=not getattr(args, "no_rf", False))
    E = H["joins"]; n2 = H["nodes_after"]
    pl = pages_fn(E, n2)
    # outputs in pipeline9's formats
    kept_rows = write_rel(args.rel, out / "rel.csv", set(E))
    write_ids(out / "badpatches_b.csv", (bad | set(H["pruned"])) & set(nodes) if args.restrict_bad else bad | set(H["pruned"]))
    with open(out / "wrap_index.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["patch", "wrap_index", "theta", "pruned", "pipeline9_flagged"])
        for p in nodes:
            k = K.get(p)
            w.writerow([p, "" if k is None else k[0], "" if k is None else round(k[1], 6), int(p in H["pruned"]), int(p in bad)])
    with open(out / "removed_joins.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["patch_a", "patch_b", "reason"])
        rfs, p9s = set(H["rf"]), set(H["after_p9"])
        for k in U:
            if k not in rfs:
                w.writerow([k[0], k[1], "wrap_index_cut"])
            elif k not in p9s:
                w.writerow([k[0], k[1], "pipeline9_modeb_patch"])
            elif k not in set(E):
                w.writerow([k[0], k[1], "pruned_minority_patch"])
    res = dict(contract="v1", n_rel_rows=len(U_all), n_joins_universe=len(U), n_rf=len(H["rf"]), n_after_pipeline9=len(H["after_p9"]),
               n_joins=len(E), rel_rows_written=kept_rows, pruned_patches=len(H["pruned"]), pages=len(pl),
               page_min_mm2=args.page_min_mm2, handedness_s=s,
               variant="(ii) pipeline9 deletions + pruning" if getattr(args, "no_rf", False) else "combined: (iii-rf) cuts + pipeline9 deletions + pruning")
    res["metrics"] = _metrics(M, args, pl, E, area, n2, repo)
    json.dump(res, open(out / "filter.json", "w"), indent=1, default=float)
    return res


def _metrics(M, args, pl, E, area, nodes, repo):
    out = {}
    kr_path = Path(args.k_ref) if args.k_ref else Path(repo) / "phase/x7/X7_v9_patch_k.csv"
    if kr_path.exists():
        kr = {int(r["patch"]): r for r in csv.DictReader(open(kr_path))}
        t = {p: int(kr[p]["k_ref"]) + (float(kr[p]["theta_from_theta0"]) % TWO_PI) / TWO_PI for p in nodes if p in kr and kr[p]["k_ref"] != ""}
        recs = M.page_records(pl, E, area, *M.cross_per_patch_layer(t), t=t)
        out["per_patch_layer"] = M.summarize(recs)
        if args.bootstrap:
            pc = {int(r["id"]): r for r in csv.DictReader(open(args.patch_table))}
            theta = {int(r["patch"]): float(r["theta_from_theta0"]) % TWO_PI for r in kr.values()}
            blk = {p: min(int(theta.get(p, 0.0) / TWO_PI * 12), 11) * 4 + min(max(int((float(pc[p]["cz"]) - 4096) / 192), 0), 3) for p in nodes}
            out["per_patch_layer_ci95"] = _boot(M, recs, blk)
        out["note_scoring"] = "per-patch-layer labels use the reference's k_ref: scored against the reference, not ground truth"
    if args.x6_pairs:
        out["x6"] = M.summarize(M.page_records(pl, E, area, *M.cross_x6(M.load_x6_labels(args.x6_pairs))))
    out["note_M1"] = ("M1 cannot rank methods: residual cross-turn joins in cleaned variants are contact-regime joins where the "
                      "reference is inconsistent (CONTRACT §5.2). The README may claim only the per-point M2 gain once P1g confirms it.")
    return out


def _boot(M, recs, blk):
    """P1e's 48-block bootstrap (seed 0, 1,000 draws), as p1e_frontier.py."""
    rng = np.random.default_rng(0); acc = {k: [] for k in ("page_area_cm2", "M1", "M2_patch", "M3_per_cm2")}
    for _ in range(1000):
        cnt = np.bincount(rng.integers(0, 48, 48), minlength=48); w = {p: float(cnt[b]) for p, b in blk.items()}
        s_ = M.summarize(recs, w)
        for k in acc:
            acc[k].append(s_[k] if s_[k] is not None else np.nan)
    return {k: [round(float(np.nanpercentile(v, 2.5)), 4), round(float(np.nanpercentile(v, 97.5)), 4)] for k, v in acc.items()}
