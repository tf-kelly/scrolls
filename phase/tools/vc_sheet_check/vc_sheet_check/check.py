"""The reference-free sheet check on one mesh (S1b (1), generalised to OBJ).

Pairs of mesh vertices 100-400 um apart ALONG the surface are snapped to the
nearest field phase-zero along the field normal and the signed sheet crossings
between them are counted (frozen phase/x2/common.py Field.snap/count, via the
frozen phase/s1b/mesh_check.py count_pairs). A correct mesh gives 0 for every
pair. Flagged: DBSCAN clusters (eps 200 um, min_samples 5) of the midpoints of
in-support pairs with round(count) != 0 -- S1b's committed thresholds.

Along-surface distance:
  tifxyz: the mesh's own row/column cumulative arc length (S1b sample_pairs,
          unmodified);
  OBJ:    shortest path along mesh edges (Dijkstra), since an OBJ has no grid.
          This is new and is flagged as such in report.json.
"""
from __future__ import annotations

import hashlib

import numpy as np

SEP_LO_UM, SEP_HI_UM = 100.0, 400.0
EPS_UM, MIN_SAMPLES = 200.0, 5
PAIRS_PER_CM2 = 400   # sampled mode's historical density (S1b); SessA-4: density per cm2 is the only knob, no floor/cap


def seed_for(name: str) -> int:
    """Stable seed. (An earlier script used hash(name), which Python
    randomises per process, so its pair draws were not reproducible.)"""
    return int.from_bytes(hashlib.sha256(name.encode()).digest()[:4], "little")


def area_cm2(mesh, um0):
    if mesh.grid is not None:
        H, W = mesh.grid.shape
        g = mesh.xyz.reshape(H, W, 3).copy(); g[~mesh.valid.reshape(H, W)] = np.nan
        # quad cells with all four corners valid: two triangles each
        a, b, c, d = g[:-1, :-1], g[:-1, 1:], g[1:, :-1], g[1:, 1:]
        t1 = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=-1)
        t2 = 0.5 * np.linalg.norm(np.cross(b - d, c - d), axis=-1)
        s = t1 + t2
        return float(np.nansum(s) * um0 ** 2 / 1e8)
    f = mesh.faces
    okf = mesh.valid[f].all(1)
    p = mesh.xyz[f[okf]]
    return float(0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1).sum() * um0 ** 2 / 1e8)


def sample_pairs_grid(mesh, um0, n, rng):
    MC = _mc()
    H, W = mesh.grid.shape
    g = mesh.xyz.reshape(H, W, 3).astype(np.float32).copy()
    ok = mesh.valid.reshape(H, W); g[~ok] = np.nan
    Su, Sv = MC.arclen_u(g, um0), MC.arclen_v(g, um0)
    pa, pb, mid, direction = MC.sample_pairs(g, ok, Su, Sv, np.ones(H, bool), SEP_LO_UM, SEP_HI_UM, n, rng)
    # recover vertex ids of the endpoints (sample_pairs returns coordinates only)
    idx = {tuple(v): i for i, v in enumerate(map(tuple, mesh.xyz.astype(np.float32)))}
    ia = np.array([idx[tuple(v)] for v in pa], np.int64) if len(pa) else np.zeros(0, np.int64)
    ib = np.array([idx[tuple(v)] for v in pb], np.int64) if len(pb) else np.zeros(0, np.int64)
    return pa, pb, mid, ia, ib


def sample_pairs_graph(mesh, um0, n, rng):
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    # graph over valid vertices only (re-indexed), so memory scales with the checked part of the mesh
    cand = np.where(mesh.valid)[0]; N = len(cand)
    loc = np.full(len(mesh.xyz), -1, np.int64); loc[cand] = np.arange(N)
    e = mesh.edges[mesh.valid[mesh.edges[:, 0]] & mesh.valid[mesh.edges[:, 1]]]
    w = np.linalg.norm(mesh.xyz[e[:, 0]] - mesh.xyz[e[:, 1]], axis=1) * um0
    a_, b_ = loc[e[:, 0]], loc[e[:, 1]]
    G = coo_matrix((np.r_[w, w], (np.r_[a_, b_], np.r_[b_, a_])), shape=(N, N)).tocsr()
    ia, ib = [], []
    tries = 0
    while len(ia) < n and tries < n * 4:
        src = rng.integers(0, N, size=min(64, n - len(ia) + 16))
        D = dijkstra(G, indices=src, limit=SEP_HI_UM)
        for k, s in enumerate(src):
            tries += 1
            d = D[k]
            tgt = rng.uniform(SEP_LO_UM, SEP_HI_UM)
            ok = np.where(np.isfinite(d) & (d >= SEP_LO_UM))[0]
            if not len(ok):
                continue
            j = ok[np.argmin(np.abs(d[ok] - tgt))]
            ia.append(int(cand[s])); ib.append(int(cand[j]))
            if len(ia) >= n:
                break
    ia, ib = np.array(ia, np.int64), np.array(ib, np.int64)
    pa = mesh.xyz[ia].astype(np.float32); pb = mesh.xyz[ib].astype(np.float32)
    return pa, pb, (pa + pb) / 2, ia, ib


def _mc():
    from ._vendor import mesh_check
    return mesh_check()


def run_check(mesh, fld, snap_tmax_l0, um0, name, n_pairs=None):
    MC = _mc()
    rng = np.random.default_rng(seed_for(name))
    A = area_cm2(mesh, um0)
    # SessA-4 (d): no 500-pair floor and no 20,000 cap (the floor raised small meshes' density above everything else's)
    n = int(n_pairs) if n_pairs is not None else int(round(A * PAIRS_PER_CM2))
    sampler = sample_pairs_grid if mesh.grid is not None else sample_pairs_graph
    if n <= 0:
        z = np.zeros((0, 3), np.float32); zi = np.zeros(0, np.int64)
        return dict(area_cm2=A, n_pairs_target=0, pa=z, pb=z, mid=z, ia=zi, ib=zi, counts=np.zeros(0), ok=np.zeros(0, bool),
                    clusters=[], flagged=np.zeros(0, bool), sampler=sampler.__name__)
    pa, pb, mid, ia, ib = sampler(mesh, um0, n, rng)
    counts, cok = MC.count_pairs(fld, pa, pb, snap_tmax_l0) if len(pa) else (np.zeros(0), np.zeros(0, bool))
    clusters, flagged = MC.cluster_flags(mid, counts, cok, EPS_UM, MIN_SAMPLES, um0) if len(pa) else ([], np.zeros(0, bool))
    return dict(area_cm2=A, n_pairs_target=n, pa=pa, pb=pb, mid=mid, ia=ia, ib=ib, counts=counts, ok=cok,
                clusters=clusters, flagged=flagged, sampler=sampler.__name__)


def per_vertex(mesh, fld, snap_tmax_l0, um0, res):
    """Per-vertex table. snap_um: signed distance along the field normal to the
    nearest phase zero (NaN when none within snap_tmax or out of support);
    pairs_tested / pairs_nonzero: in-support pairs with this vertex as an
    endpoint; in_cluster: vertex within EPS_UM of a flagged pair midpoint that
    belongs to a DBSCAN cluster."""
    from scipy.spatial import cKDTree
    N = len(mesh.xyz)
    snap_um = np.full(N, np.nan)
    v = np.where(mesh.valid)[0]
    for k in range(0, len(v), 200000):
        sl = v[k:k + 200000]
        _, t = fld.snap(mesh.xyz[sl].astype(np.float32), tmax=snap_tmax_l0)
        snap_um[sl] = t * um0
    tested = np.zeros(N, np.int32); nonzero = np.zeros(N, np.int32)
    good = res["ok"] & np.isfinite(res["counts"])
    nz = good & (np.round(res["counts"]) != 0)
    for arr, m in ((tested, good), (nonzero, nz)):
        np.add.at(arr, res["ia"][m], 1); np.add.at(arr, res["ib"][m], 1)
    in_cluster = np.zeros(N, bool)
    cid = np.full(N, -1, np.int32)
    if res["clusters"]:
        from sklearn.cluster import DBSCAN
        pts = res["mid"][res["flagged"]] * um0
        lab = DBSCAN(eps=EPS_UM, min_samples=MIN_SAMPLES).fit(pts).labels_
        core = pts[lab >= 0]; corelab = lab[lab >= 0]
        tree = cKDTree(core)
        d, j = tree.query(mesh.xyz[v] * um0, distance_upper_bound=EPS_UM)
        hit = np.isfinite(d)
        in_cluster[v[hit]] = True; cid[v[hit]] = corelab[j[hit]]
    return dict(snap_um=snap_um, pairs_tested=tested, pairs_nonzero=nonzero, in_cluster=in_cluster, cluster_id=cid)


# ------------------------------------------------------------------------------------------------ dense (SessA-4)

def dense_pairs(mesh, um0, lo_um=SEP_LO_UM, hi_um=SEP_HI_UM, batch=512):
    """Every pair of valid vertices whose shortest path along mesh edges is in [lo_um, hi_um] (the same
    100-400 um S1b samples from, taken exhaustively). Dijkstra on the valid-vertex edge graph, in source batches so
    memory is batch x N distances. Returns global vertex ids (ia < ib by construction of the graph order)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    cand = np.where(mesh.valid)[0]; N = len(cand)
    loc = np.full(len(mesh.xyz), -1, np.int64); loc[cand] = np.arange(N)
    e = mesh.edges[mesh.valid[mesh.edges[:, 0]] & mesh.valid[mesh.edges[:, 1]]]
    w = np.linalg.norm(mesh.xyz[e[:, 0]] - mesh.xyz[e[:, 1]], axis=1) * um0
    a_, b_ = loc[e[:, 0]], loc[e[:, 1]]
    G = coo_matrix((np.r_[w, w], (np.r_[a_, b_], np.r_[b_, a_])), shape=(N, N)).tocsr()
    IA, IB, DD = [], [], []
    for s0 in range(0, N, batch):
        src = np.arange(s0, min(s0 + batch, N))
        D = dijkstra(G, indices=src, limit=hi_um)
        r, c = np.nonzero(np.isfinite(D) & (D >= lo_um) & (D <= hi_um))
        keep = c > src[r]
        IA.append(cand[src[r[keep]]]); IB.append(cand[c[keep]]); DD.append(D[r[keep], c[keep]])
    return np.concatenate(IA), np.concatenate(IB), np.concatenate(DD)


def snap_vertices(mesh, fld, snap_tmax_l0, idx=None):
    """Snapped position (L0 xyz, NaN where no phase zero in support within the snap range) for every valid vertex
    (or the given ids). Snapping is per point and deterministic, so this equals S1b's per-pair snapping."""
    S = np.full(mesh.xyz.shape, np.nan)
    v = np.where(mesh.valid)[0] if idx is None else np.asarray(idx)
    if len(v):
        S[v], _ = fld.snap(mesh.xyz[v].astype(np.float32), tmax=snap_tmax_l0)
    return S


def count_dense(fld, S, ia, ib):
    """Signed crossing counts between snapped endpoints; ok = both snapped and the path stayed in support.

    The frozen Field.count sorts pairs by length and samples each chunk of 4,000 at the chunk's LONGEST path's sample
    count, so a pair's result depends on which pairs share its chunk (found in SessA-4 when a subset recount did not
    reproduce the full run). Here Field.count is called once per group of pairs with the same per-pair sample count
    (ceil(L / 0.5) + 2, L in field voxels, Field.count's own formula), so every pair's samples depend only on itself
    and any subset recount reproduces the full run exactly."""
    from ._vendor import mesh_check
    counts = np.full(len(ia), np.nan); ok = np.zeros(len(ia), bool)
    both = np.where(np.isfinite(S[ia]).all(1) & np.isfinite(S[ib]).all(1))[0]
    if len(both):
        A_ = S[ia[both]].astype(np.float32); B_ = S[ib[both]].astype(np.float32)
        slab = mesh_check().common.slab
        L = np.linalg.norm(slab(B_) - slab(A_), axis=1); ns = (np.ceil(L / 0.5) + 2).astype(int)
        for n in np.unique(ns):
            g = np.where(ns == n)[0]
            c_, o_ = fld.count(A_[g], B_[g])
            counts[both[g]] = c_; ok[both[g[o_]]] = True
    return counts, ok


def run_dense(mesh, fld, snap_tmax_l0, um0):
    import time
    t0 = time.time(); ia, ib, dd = dense_pairs(mesh, um0); t_pairs = time.time() - t0
    t0 = time.time(); S = snap_vertices(mesh, fld, snap_tmax_l0); t_snap = time.time() - t0
    t0 = time.time(); counts, ok = count_dense(fld, S, ia, ib); t_count = time.time() - t0
    mid = (mesh.xyz[ia] + mesh.xyz[ib]) / 2
    return dict(ia=ia, ib=ib, geodesic_um=dd, S=S, counts=counts, ok=ok, mid=mid, pa=mesh.xyz[ia], pb=mesh.xyz[ib],
                area_cm2=area_cm2(mesh, um0), timing=dict(pairs_s=t_pairs, snap_s=t_snap, count_s=t_count),
                sampler="dense")


def clusters_at(mid_l0, flagged, um0, m, eps_um=EPS_UM):
    """DBSCAN(eps, min_samples=m) on flagged midpoints (um). Returns labels over the flagged subset (-1 noise)."""
    from sklearn.cluster import DBSCAN
    pts = mid_l0[flagged] * um0
    if len(pts) == 0:
        return np.zeros(0, int)
    return DBSCAN(eps=eps_um, min_samples=m).fit(pts).labels_
