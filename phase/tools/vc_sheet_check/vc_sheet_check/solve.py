"""Wrap-index solve (contract §2): Q3c's reference-free uniform-weight consensus, with the spacing as a parameter.

Ported from <branch> 0f5aa76 (the source of phase/p1page/p1b_q3c_k.csv):
  phase/q3/q3_common.py build_full_state   -> edges_from_slab2 + build_state (d_i, d_ii, stevens, theta)
  phase/q3/q3c_deploy.py choose_handedness, build_terms_reffree, uniform_weight -> same names here
  phase/h1/refmesh.py build_axis, ang, cross -> same names here (RefMesh itself is not needed: it only
      supplies k_ref, the reference-mesh wrap number, which the reference-free solve never reads)
  phase/h1/our_solver.py lp_synchronise -> vendored unmodified (_vendor/our_solver.py)

The spacing SP enters in exactly two places: d_ii = round(sep_ii / SP) and stevens = max_sep > 0.59 * SP.
Q3c used SP = 134.0 um (a constant withdrawn as a measured period; CONTRACT A7.5). `edges_from_witness` builds
the same edge records from a region's own witness (X6 truth.py's point sampling: <= 10 evaluated points per
non-coincident pair, default_rng(6), in pair order).

Term convention (our_solver): (a, b, d, w) means d ~ k_b - k_a.
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import numpy as np

VOX_UM = 7.91
SP_UM_Q3C = 134.0
STEVENS_FRAC = 0.59
TH0 = 0.0


# ---------------- axis and angles (phase/h1/refmesh.py, unchanged logic) ----------------
def build_axis(nodes, table):
    """refmesh.build_axis: node patch centroids, n-weighted, 256-voxel z bins, interpolated, smoothed (width 3).
    `table`: {int id: row with cx, cy, cz, n}. Returns axis_xy(z) -> (x, y)."""
    from scipy.ndimage import uniform_filter1d
    pid = [int(p) for p in nodes]
    c = np.array([[float(table[p]["cx"]), float(table[p]["cy"]), float(table[p]["cz"])] for p in pid])
    n_pts = np.array([float(table[p]["n"]) for p in pid])
    zb = np.arange(np.floor(c[:, 2].min() / 256) * 256, c[:, 2].max() + 256, 256)
    ax_x = np.full(len(zb) - 1, np.nan)
    ax_y = np.full(len(zb) - 1, np.nan)
    for i in range(len(zb) - 1):
        m = (c[:, 2] >= zb[i]) & (c[:, 2] < zb[i + 1])
        if m.any():
            ax_x[i] = np.average(c[m, 0], weights=n_pts[m])
            ax_y[i] = np.average(c[m, 1], weights=n_pts[m])
    ok = np.isfinite(ax_x)
    zc = (zb[:-1] + zb[1:]) / 2
    ax_x = uniform_filter1d(np.interp(zc, zc[ok], ax_x[ok]), 3, mode="nearest")
    ax_y = uniform_filter1d(np.interp(zc, zc[ok], ax_y[ok]), 3, mode="nearest")

    def axis_xy(z):
        return np.interp(z, zc, ax_x), np.interp(z, zc, ax_y)

    return axis_xy


def ang(p, axis_xy):
    ax_, ay_ = axis_xy(p[..., 2])
    return np.mod(np.arctan2(p[..., 1] - ay_, p[..., 0] - ax_) - TH0, 2 * np.pi)


def cross(t1, t2):
    e = t1 + (np.mod(t2 - t1 + np.pi, 2 * np.pi) - np.pi)
    return np.where(e >= 2 * np.pi, 1, np.where(e < 0, -1, 0))


def radial_sep_um(PA, PB, axis_xy):
    """(PB - PA) . r_hat * 7.91, r_hat radial from the axis at the midpoint (x, y, z points)."""
    mid = (PA + PB) / 2
    mx, my = axis_xy(mid[:, 2])
    r_hat = np.stack([mid[:, 0] - mx, mid[:, 1] - my, np.zeros(len(mid))], axis=1)
    r_hat /= (np.linalg.norm(r_hat, axis=1, keepdims=True) + 1e-12)
    return np.einsum("ij,ij->i", PB - PA, r_hat) * VOX_UM


def _pair_medians(pair_idx, vals):
    order = np.argsort(pair_idx, kind="stable")
    ps, vs = pair_idx[order], vals[order]
    bounds = np.searchsorted(ps, np.arange(ps.max() + 2)) if len(ps) else np.zeros(1, int)
    out = {}
    for i in range(len(bounds) - 1):
        lo, hi = bounds[i], bounds[i + 1]
        if hi > lo:
            out[i] = float(np.median(vs[lo:hi]))
    return out


# ---------------- edge records ----------------
# edge: dict(a, b [int patch ids, in the source's pair order], d_i [int|None], sep_ii_um [float|None], msep_um [float])

def edges_from_slab2(repo):
    """Q3c's own inputs: phase/x6/x6b_pairs.csv (edges, max_sep_um), x6b_points.npz (sep_ii),
    phase/x3/results/slab2/pairs.csv (d_i = median_count, coincident excluded, sign flipped when swapped),
    phase/x1/patches.csv (centroids for the axis and theta)."""
    R = Path(repo)
    x6b = list(csv.DictReader(open(R / "phase/x6/x6b_pairs.csv")))
    table = {int(r["id"]): r for r in csv.DictReader(open(R / "phase/x1/patches.csv"))}
    nodes = sorted({int(r["patch_a"]) for r in x6b} | {int(r["patch_b"]) for r in x6b})
    axis_xy = build_axis(nodes, table)
    pts = np.load(R / "phase/x6/x6b_points.npz")
    sep_ii = _pair_medians(pts["pair"], radial_sep_um(pts["PA"], pts["PB"], axis_xy))
    slab2 = {(r["patch_a"], r["patch_b"]): r for r in csv.DictReader(open(R / "phase/x3/results/slab2/pairs.csv"))
             if r["verdict"] != "coincident"}
    E = []
    for i, r in enumerate(x6b):
        a, b = r["patch_a"], r["patch_b"]
        j = slab2.get((a, b)) or slab2.get((b, a))
        swapped = j is not None and (a, b) not in slab2
        d_i = None
        if j is not None and j["median_count"] != "":
            d_i = int(j["median_count"]) * (-1 if swapped else 1)
        E.append(dict(a=int(a), b=int(b), d_i=d_i, sep_ii_um=sep_ii.get(i), msep_um=float(r["max_sep_um"])))
    xyz = {p: np.array([float(table[p][c]) for c in ("cx", "cy", "cz")]) for p in nodes}
    return E, nodes, xyz, axis_xy


def edges_from_witness(P, meta, W, MED, verdict, axis_xy, seed=6, n_pts=10, NT=None, AG=None, return_points=False):
    """Region edges from its own witness, X6 truth.py's rule: every non-coincident pair with >= 1 evaluated point
    (witness sep > 1 voxel); <= n_pts of those points drawn with one default_rng(seed) stream in pair order;
    sep_ii = median radial separation; msep = max normal separation x 7.91 (rounded to 0.1 um as in x6b_pairs.csv);
    d_i = the pair's median crossing count where testable. P/W points are (x, y, z) L0."""
    rng = np.random.default_rng(seed)
    o = np.argsort(W["pi"], kind="stable"); cut = np.searchsorted(W["pi"][o], np.arange(len(meta) + 1))
    E, PA_, PB_, pidx = [], [], [], []
    for q, (a, b) in enumerate(meta):
        if verdict[q] == "coincident":
            continue
        jj = o[cut[q]:cut[q + 1]]
        if not len(jj):
            continue
        ms = round(float(np.max(W["sep"][jj])) * VOX_UM, 1)
        jj = rng.choice(jj, min(n_pts, len(jj)), replace=False)
        n = len(E)
        PA_.append(P["PA"][W["ia"][jj]]); PB_.append(P["PB"][W["ia"][jj]]); pidx.append(np.full(len(jj), n))
        E.append(dict(a=int(a), b=int(b), d_i=None if not np.isfinite(MED[q]) else int(MED[q]), sep_ii_um=None, msep_um=ms,
                      verdict=str(verdict[q]), n_testable=None if NT is None else int(NT[q]),
                      agreement=None if AG is None or not np.isfinite(AG[q]) else float(AG[q])))
    if E:
        PA_, PB_, pidx = np.concatenate(PA_).astype(float), np.concatenate(PB_).astype(float), np.concatenate(pidx)
        med = _pair_medians(pidx, radial_sep_um(PA_, PB_, axis_xy))
        for i, e in enumerate(E):
            e["sep_ii_um"] = med.get(i)
    nodes = sorted({e["a"] for e in E} | {e["b"] for e in E})
    if return_points:                 # the sampled points themselves (X6's rule), label-free: coordinates and edge index
        return E, nodes, (PA_ if E else np.zeros((0, 3))), (PB_ if E else np.zeros((0, 3))), (pidx if E else np.zeros(0, int))
    return E, nodes


# ---------------- state, terms, solve (q3c_deploy.py) ----------------
def build_state(E, nodes, xyz, axis_xy, spacing_um, terms=("i", "ii", "iii")):
    """terms: which measurements enter the LP (SessA-7): 'i' crossing counts, 'ii' radial separation / spacing,
    'iii' the Stevens / same-wrap term. Q3c uses all three."""
    pos = {int(p): i for i, p in enumerate(nodes)}
    Es = []
    for e in E:
        d_ii = int(round(e["sep_ii_um"] / spacing_um)) if e["sep_ii_um"] is not None else None
        Es.append(dict(e, d_ii=d_ii, stevens=e["msep_um"] > STEVENS_FRAC * spacing_um))
    X = np.array([xyz[int(p)] for p in nodes], float).reshape(-1, 3)
    thN = ang(X, axis_xy)
    axx, axy = axis_xy(X[:, 2]); rho = np.hypot(X[:, 0] - np.asarray(axx), X[:, 1] - np.asarray(axy))   # tie-break r_i (SessA-15)
    return dict(pos=pos, N=len(nodes), E=Es, thN=thN, rho=rho, nodes=[int(p) for p in nodes], spacing_um=float(spacing_um),
                terms=tuple(terms))


def uniform_weight(e, kind):
    return 1.0


def cut_adj(d, a, b, thN, s):
    c = int(cross(thN[a:a + 1], thN[b:b + 1])[0])
    return d + s * c


def build_ab_terms(state, weight_fn, s, meta=None):
    """meta: optional list; one (edge, type) record is appended per term, in term order (SessA-8 unsatisfied.csv)."""
    pos, thN = state["pos"], state["thN"]
    terms = []
    for e in state["E"]:
        a, b = pos[e["a"]], pos[e["b"]]
        use = state.get("terms", ("i", "ii", "iii"))
        if e["d_ii"] is not None and "ii" in use:
            terms.append((a, b, cut_adj(e["d_ii"], a, b, thN, s), weight_fn(e, "ii")))
            if meta is not None: meta.append((e, "ii"))
        if e["d_i"] is not None and "i" in use:
            terms.append((a, b, cut_adj(e["d_i"], a, b, thN, s), weight_fn(e, "i")))
            if meta is not None: meta.append((e, "i"))
    return terms


VOX_UM = 7.91


def tiebreak_r(state, terms):
    """SessA-15 tie-break targets: r_i = round((rho_i - rho_A) / SP_vox), rho = the centroid's distance from the solve axis,
    A = the anchor (smallest node index) of the largest primary component of these terms. No s factor (d_ii has none)."""
    from ._vendor import our_solver
    lab, _ = our_solver.anchors_per_component(terms, state["N"])
    big = np.bincount(lab).argmax(); A = int(np.where(lab == big)[0].min())
    return np.rint((state["rho"] - state["rho"][A]) / (state["spacing_um"] / VOX_UM)).astype(np.int64), A


def lp_call(state, terms, tiebreak, info=None):
    """(k, labels, primary objective) of one vertex-relevant LP call: the tie-broken circulation (default, SessA-15) or
    the committed HiGHS path (tiebreak=False)."""
    from ._vendor import our_solver
    if not tiebreak:
        return our_solver.lp_synchronise(terms, state["N"])
    from . import circulation as CIRC
    r, A = tiebreak_r(state, terms)
    k, lab, obj, inf = CIRC.solve_tiebreak(terms, state["N"], r)
    if info is not None:
        info.append(dict(inf, anchor_node=state["nodes"][A], k_anchor=int(k[A]), n_terms=len(terms)))
    return k, lab, obj


def choose_handedness(state, weight_fn, tiebreak=False):
    """Only the two optimal OBJECTIVES are used, and optimal objectives are unique: with tiebreak the plain circulation."""
    from ._vendor import our_solver
    objs = {}
    for s in (1, -1):
        terms = build_ab_terms(state, weight_fn, s)
        if tiebreak:
            from . import circulation as CIRC
            objs[s] = CIRC.solve_plain(terms, state["N"])[2]
        else:
            _, _, obj = our_solver.lp_synchronise(terms, state["N"])
            objs[s] = obj
    return (1 if objs[1] <= objs[-1] else -1), objs


def build_terms_reffree(state, weight_fn, s, meta=None, tiebreak=False, info=None):
    pos = state["pos"]
    terms_ab = build_ab_terms(state, weight_fn, s, meta)
    kA, _, _ = lp_call(state, terms_ab, tiebreak, info)
    T3 = list(terms_ab)
    if "iii" not in state.get("terms", ("i", "ii", "iii")):
        return T3
    for e in state["E"]:
        a, b = pos[e["a"]], pos[e["b"]]
        if e["stevens"]:
            raw = kA[b] - kA[a]
            target = int(np.sign(raw)) if raw != 0 else 1
        else:
            target = 0
        T3.append((a, b, cut_adj(target, a, b, state["thN"], s), weight_fn(e, "iii")))
        if meta is not None: meta.append((e, "iii"))
    return T3


def solve(state, weight_fn=uniform_weight, tiebreak=True):
    """-> dict(k, component, s_chosen, objectives, objective, n, n_components, cpu_s).
    tiebreak=True (default from SessA-15, the project owner's ruling): the kA and final calls minimise primary + (1/4M) sum |k - r| by
    the circulation; handedness by the plain circulation's objectives. tiebreak=False: the committed HiGHS path (Q3c)."""
    t0 = time.process_time(); tb = []
    s_best, objs = choose_handedness(state, weight_fn, tiebreak)
    meta = []
    T3 = build_terms_reffree(state, weight_fn, s_best, meta, tiebreak, tb)
    k, lab, obj = lp_call(state, T3, tiebreak, tb)
    if k is None:
        raise RuntimeError("LP solve failed")
    uns = []
    for (a, b, d, w), (e, typ) in zip(T3, meta):
        dk = int(round(k[b] - k[a]))
        if dk != d:
            uns.append(dict(patch_a=e["a"], patch_b=e["b"], type=typ, observed=int(d), solved=dk, residual=dk - int(d), weight=w,
                            sep_ii_um=e.get("sep_ii_um"), max_sep_um=e.get("msep_um"), n_testable=e.get("n_testable"),
                            agreement=e.get("agreement"), verdict=e.get("verdict"), d_i=e.get("d_i"), d_ii=e.get("d_ii"),
                            stevens=e.get("stevens")))
    return dict(k=np.asarray(k), component=np.asarray(lab), s_chosen=int(s_best), unsatisfied=uns,
                n_unsatisfied=len(uns), n_unsatisfied_by_type={t: sum(u["type"] == t for u in uns) for t in ("i", "ii", "iii")},
                objectives={str(a): float(b) for a, b in objs.items()}, objective=float(obj), n=int(state["N"]),
                n_components=int(len(set(np.asarray(lab).tolist()))), n_terms=len(T3),
                spacing_um=state["spacing_um"], terms=list(state.get("terms", ())), cpu_s=round(time.process_time() - t0, 1),
                tiebreak=(dict(rule="SessA-15 (project owner, 2026-09-28): minimise primary + eps*sum|k_i - r_i|, eps = 1/(4M); r_i = round((rho_i - rho_A)/SP_vox), A = anchor of the largest component; circulation with a virtual anchor",
                               calls=tb) if tiebreak else None))


def write_wrap_index(out_csv, state, res, extra=None):
    """p1b_q3c_k.csv format (patch, k_q3c, component, thN) + a JSON sidecar like p1b_q3c_k.json."""
    out_csv = Path(out_csv); out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["patch", "k_q3c", "component", "thN"])
        for i, p in enumerate(state["nodes"]):
            w.writerow([p, int(round(res["k"][i])), int(res["component"][i]), round(float(state["thN"][i]), 6)])
    meta = {k: v for k, v in res.items() if k not in ("k", "component", "unsatisfied")}
    write_unsatisfied(out_csv.parent / "unsatisfied.csv", res.get("unsatisfied", []))
    meta["source"] = "vc_sheet_check solve (Q3c reference-free uniform weight, <branch> 0f5aa76 port)"
    meta.update(extra or {})
    json.dump(meta, open(out_csv.with_suffix(".json"), "w"), indent=1)
    return meta


UNSAT_COLS = ["patch_a", "patch_b", "type", "observed", "solved", "residual", "weight", "sep_ii_um", "max_sep_um",
              "n_testable", "agreement", "verdict", "d_i", "d_ii", "stevens"]


def write_unsatisfied(path, uns):
    """Every LP term the solution leaves violated (k_b - k_a != cut-adjusted target), one row per term (SessA-8)."""
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=UNSAT_COLS, extrasaction="ignore"); w.writeheader()
        for u in uns:
            w.writerow({k: ("" if v is None else (round(v, 3) if isinstance(v, float) else v)) for k, v in u.items()})


def compare_up_to_component_constant(K_ref, comp_ref, K_new):
    """Share of common patches whose k equals the reference's after removing one constant per reference component
    (the modal difference within that component)."""
    common = [p for p in K_ref if p in K_new]
    by = {}
    for p in common:
        by.setdefault(comp_ref[p], []).append(p)
    same = 0; per = {}
    for c, ps in by.items():
        d = np.array([K_new[p] - K_ref[p] for p in ps])
        v, n = np.unique(d, return_counts=True); m = v[np.argmax(n)]
        s = int((d == m).sum()); same += s; per[str(c)] = dict(n=len(ps), agree=s, offset=int(m))
    return dict(common=len(common), agree=same, frac=same / max(len(common), 1), per_component=per)


# ---------------- persistence and CLI ----------------
def save_edges(path, E, nodes, xyz, axis_file, vertex_sample_xyz=None, extra=None):
    d = dict(edges=E, nodes=[int(p) for p in nodes], centroids_xyz={str(p): [float(v) for v in xyz[p]] for p in nodes},
             axis_file=str(axis_file), vertex_sample_xyz=None if vertex_sample_xyz is None else np.asarray(vertex_sample_xyz).round(2).tolist())
    d.update(extra or {})
    json.dump(d, open(path, "w"))


def load_edges(path):
    d = json.load(open(path))
    from .field import load_axis_file
    xyz = {int(p): np.array(v) for p, v in d["centroids_xyz"].items()}
    ax = Path(d["axis_file"])
    if not ax.exists() and (Path(path).parent / ax.name).exists():      # committed inputs: the axis file sits beside the edges (open item 50)
        ax = Path(path).parent / ax.name
    return d["edges"], d["nodes"], xyz, load_axis_file(ax), d


def resolve_spacing(spec, ct_spec, points_xyz, scan_shape, log=print):
    if str(spec).lower() != "estimate":
        return float(spec), None
    from . import sources as SRC, spacing as SPC
    est = SPC.estimate(SRC.CT(ct_spec, 0), points_xyz, scan_shape, log=log)
    return float(est["spacing_um"]), est


def read_wrap_index(path):
    K, C = {}, {}
    for r in csv.DictReader(open(path)):
        K[int(r["patch"])] = int(r["k_q3c"]); C[int(r["patch"])] = r["component"]
    return K, C


def cli(a, repo):
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if a.slab2:
        E, nodes, xyz, axis_xy = edges_from_slab2(repo)
        pts = np.load(Path(repo) / "phase/x6/x6b_points.npz")["PA"]
        src = "committed slab-2 inputs (phase/x6/x6b_pairs.csv, x6b_points.npz, phase/x3/results/slab2/pairs.csv, phase/x1/patches.csv)"
    else:
        E, nodes, xyz, axis_xy, d = load_edges(a.edges)
        pts = np.array(d.get("vertex_sample_xyz") or [xyz[p] for p in nodes])
        src = f"edges {a.edges}"
    if getattr(a, "features", None):                     # testability columns for unsatisfied.csv from a run's features
        F = {(int(r["patch_a"]), int(r["patch_b"])): r for r in csv.DictReader(open(a.features))}
        for e in E:
            r = F.get((min(e["a"], e["b"]), max(e["a"], e["b"])))
            if r:
                for k_, v_ in (("verdict", r["verdict"]), ("n_testable", int(r["n_testable"])),
                               ("agreement", float(r["agreement"]) if r["agreement"] not in ("", "nan") else None)):
                    if e.get(k_) is None:
                        e[k_] = v_
    sp, est = resolve_spacing(a.spacing_um, a.ct, pts, a.scan_shape)
    st = build_state(E, nodes, xyz, axis_xy, sp, terms=tuple(a.terms.split(",")))
    res = solve(st, tiebreak=not getattr(a, "no_tiebreak", False))
    extra = dict(inputs=src, spacing_estimate=est, n_edges=len(E),
                 n_d_i=sum(e["d_i"] is not None for e in E), n_d_ii=sum(e["d_ii"] is not None for e in st["E"]),
                 n_stevens=sum(e["stevens"] for e in st["E"]))
    if a.compare:
        Kr, Cr = read_wrap_index(a.compare)
        Kn = {p: int(round(res["k"][i])) for i, p in enumerate(st["nodes"])}
        extra["compare"] = dict(against=a.compare, **compare_up_to_component_constant(Kr, Cr, Kn))
    return write_wrap_index(out / "wrap_index.csv", st, res, extra)
