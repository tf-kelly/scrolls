"""STAND-IN for the planned A3 orient(): orientation by continuity in 3D.

NOT phase/core. Same call shape as the contract's orient(normal_unit, c, psi=None, chunk, out)
-> (normal_oriented, psi_signed), plus keyword-only extras (amp, support, cell, frust_max, info).
If it proves useful it moves into core as A3 unchanged.

Method (M1c gauge in 3D, 8-voxel cells):
  cells     8^3 voxels; cell normal = principal axis of the amplitude-weighted structure tensor
            of the unit normals over supported voxels; a cell is valid if >= 25 % supported.
  graph     26-neighbour edges between valid cells, weight w = a_i a_j |n_i.n_j|,
            sign s = sign(n_i.n_j).
  gauge     maximum spanning forest; signs propagated from each tree's highest-amplitude cell;
            5 sweeps of weighted majority vote over all edges; each component's global sign
            set so the amplitude-weighted mean of n.r_hat (r_hat radial from c(z)) is positive.
            That last rule is the radial rule at component scale (see M2.md).
  mask      cells whose local frustration (disagreeing edge weight / own edge weight) > frust_max
            leave the support.
  voxels    sigma = sigma_cell * sign(n_voxel . n_cell); normal_oriented = sigma n;
            psi_signed = psi_u where sigma > 0 else (1 - psi_u) mod 1 (contract).
Outputs (when out is given, zarr format 2): normal_oriented int8 (x127), psi_signed uint8
(turns x 256), oriented_support uint8.
"""
from __future__ import annotations
import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import minimum_spanning_tree, connected_components

OFFS = [(dz, dy, dx) for dz in (-1, 0, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dz, dy, dx) > (0, 0, 0)]
PAIRS = [(0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2)]


def _zarr_out(out, name, shape, dtype, chunk=128):
    import zarr
    return zarr.open_array(f"{out}/{name}", mode="w", shape=shape, dtype=dtype, zarr_format=2,
                           chunks=tuple(shape[:-3]) + (chunk,) * 3)


def _cells(normal_unit, amp, support, cell, chunk):
    Z, Y, X = amp.shape
    nc = [int(np.ceil(s / cell)) for s in (Z, Y, X)]
    T = np.zeros((6,) + tuple(nc), np.float64); A = np.zeros(nc); C = np.zeros(nc)
    for z0 in range(0, Z, chunk):
        for y0 in range(0, Y, chunk):
            for x0 in range(0, X, chunk):
                sl = (slice(z0, min(z0 + chunk, Z)), slice(y0, min(y0 + chunk, Y)), slice(x0, min(x0 + chunk, X)))
                s = np.asarray(support[sl]) > 0
                if not s.any():
                    continue
                a = np.asarray(amp[sl], np.float32) * s
                n = np.asarray(normal_unit[(slice(None),) + sl], np.float32)
                sh = s.shape; pz, py, px = [(-d) % cell for d in sh]
                pad = lambda v: np.pad(v, [(0, 0)] * (v.ndim - 3) + [(0, pz), (0, py), (0, px)])
                a, s, n = pad(a), pad(s.astype(np.float32)), pad(n)
                bz, by, bx = [d // cell for d in a.shape]
                red = lambda v: v.reshape(bz, cell, by, cell, bx, cell).sum((1, 3, 5))
                cz, cy, cx = z0 // cell, y0 // cell, x0 // cell
                tgt = (slice(cz, cz + bz), slice(cy, cy + by), slice(cx, cx + bx))
                tz = (slice(0, min(bz, nc[0] - cz)), slice(0, min(by, nc[1] - cy)), slice(0, min(bx, nc[2] - cx)))
                tgt = tuple(slice(t.start, t.start + u.stop) for t, u in zip(tgt, tz))
                A[tgt] += red(a)[tz]; C[tgt] += red(s)[tz]
                for k, (i, j) in enumerate(PAIRS):
                    T[(k,) + tgt] += red(a * n[i] * n[j])[tz]
    ok = C >= 0.25 * cell ** 3
    M = np.zeros(tuple(nc) + (3, 3))
    for k, (i, j) in enumerate(PAIRS):
        M[..., i, j] = T[k]; M[..., j, i] = T[k]
    w, v = np.linalg.eigh(M[ok])
    cn = np.zeros(tuple(nc) + (3,), np.float32); cn[ok] = v[:, :, -1]
    camp = np.where(C > 0, A / np.maximum(C, 1), 0)
    return ok, cn, camp.astype(np.float32), C


def _edges(ok, cn, camp):
    idx = -np.ones(ok.shape, np.int64); idx[ok] = np.arange(ok.sum())
    I, J, W, S = [], [], [], []
    for d in OFFS:
        A = tuple(slice(max(0, -o), s - max(0, o)) for o, s in zip(d, ok.shape))
        B = tuple(slice(max(0, o), s - max(0, -o)) for o, s in zip(d, ok.shape))
        m = ok[A] & ok[B]
        dot = np.sum(cn[A][m] * cn[B][m], axis=-1)
        I.append(idx[A][m]); J.append(idx[B][m])
        W.append((camp[A][m] * camp[B][m] * np.abs(dot)).astype(np.float32) + 1e-9)
        S.append(np.where(dot >= 0, 1, -1).astype(np.int8))
    return idx, np.concatenate(I), np.concatenate(J), np.concatenate(W), np.concatenate(S)


def _gauge(n, I, J, W, S, camp_v, nr_v):
    G = sparse.coo_matrix((-W, (I, J)), shape=(n, n)).tocsr()
    T = minimum_spanning_tree(G).tocoo()                        # max spanning forest
    tI, tJ = T.row, T.col
    Sm = sparse.coo_matrix((S.astype(np.float32), (I, J)), shape=(n, n)).tocsr()
    tS = np.asarray(Sm[tI, tJ]).ravel()
    ncomp, lab = connected_components(sparse.coo_matrix((np.ones(len(tI)), (tI, tJ)), shape=(n, n)), directed=False)
    sig = np.zeros(n, np.float32)
    best = np.full(ncomp, -1.0); root = np.zeros(ncomp, np.int64)
    order = np.argsort(camp_v)
    root[lab[order]] = order                                     # last write wins = highest amp
    sig[root] = 1
    while True:                                                  # vectorised BFS over the forest
        a = (sig[tI] != 0) & (sig[tJ] == 0); b = (sig[tJ] != 0) & (sig[tI] == 0)
        if not (a.any() or b.any()):
            break
        sig[tJ[a]] = sig[tI[a]] * tS[a]; sig[tI[b]] = sig[tJ[b]] * tS[b]
    Am = sparse.coo_matrix((W * S, (I, J)), shape=(n, n)).tocsr(); Am = Am + Am.T
    for _ in range(5):
        v = Am @ sig; sig = np.where(v != 0, np.sign(v), sig).astype(np.float32)
    flip = np.bincount(lab, camp_v * sig * nr_v, ncomp) < 0
    sig[flip[lab]] *= -1
    bad = sig[I] * sig[J] * S < 0
    tot = np.bincount(I, W, n) + np.bincount(J, W, n)
    badw = np.bincount(I[bad], W[bad], n) + np.bincount(J[bad], W[bad], n)
    return sig, lab, ncomp, float(W[bad].sum() / W.sum()), badw / np.maximum(tot, 1e-12)


def orient(normal_unit, c, psi=None, chunk=128, out=None, *, amp=None, support=None,
           cell=8, frust_max=0.2, info=None):
    Z, Y, X = normal_unit.shape[-3:]
    amp = amp if amp is not None else np.ones((Z, Y, X), np.float32)
    support = support if support is not None else np.ones((Z, Y, X), np.uint8)
    ok, cn, camp, cnt = _cells(normal_unit, amp, support, cell, chunk)
    idx, I, J, W, S = _edges(ok, cn, camp)
    n = int(ok.sum())
    zz, yy, xx = np.nonzero(ok)
    zc = np.clip(((zz + 0.5) * cell).astype(int), 0, len(c) - 1)
    ry, rx = (yy + 0.5) * cell - c[zc, 0], (xx + 0.5) * cell - c[zc, 1]
    rr = np.hypot(ry, rx) + 1e-9
    nr = (cn[ok][:, 1] * ry + cn[ok][:, 2] * rx) / rr
    ncomp_pre, _ = connected_components(sparse.coo_matrix((np.ones(len(I)), (I, J)), shape=(n, n)), directed=False)
    sig, lab, ncomp_forest, frus, local = _gauge(n, I, J, W, S, camp[ok], nr)
    keep = local <= frust_max
    kI = keep[I] & keep[J]
    ncomp_post, lab_post = connected_components(sparse.coo_matrix((np.ones(kI.sum()), (I[kI], J[kI])), shape=(n, n)), directed=False)
    vox = cnt[ok]
    comp_vox = np.bincount(lab_post[keep], vox[keep], ncomp_post)
    big = np.argsort(comp_vox)[::-1]
    cellsig = np.zeros(ok.shape, np.float32); cellsig[ok] = np.where(keep, sig, 0)
    cellbig = np.zeros(ok.shape, bool); cellbig[ok] = keep & (lab_post == big[0])
    if info is not None:
        info.update(cell=cell, n_cells_valid=n, n_edges=int(len(I)), components_before_gauge=int(ncomp_pre),
                    forest_components=int(ncomp_forest), frustration=frus,
                    masked_cells=int((~keep).sum()), masked_cell_frac=float((~keep).mean()),
                    masked_voxel_frac=float(vox[~keep].sum() / vox.sum()),
                    components_after_mask=int(ncomp_post),
                    largest_share=float(comp_vox[big[0]] / comp_vox.sum()),
                    second_share=float(comp_vox[big[1]] / comp_vox.sum()) if ncomp_post > 1 else 0.0,
                    local_frustration=local, cell_ok=ok)
    if out is None:
        return cellsig, cellbig
    no = _zarr_out(out, "normal_oriented", (3, Z, Y, X), np.int8, chunk)
    po = _zarr_out(out, "psi_signed", (Z, Y, X), np.uint8, chunk) if psi is not None else None
    so = _zarr_out(out, "oriented_support", (Z, Y, X), np.uint8, chunk)
    bo = _zarr_out(out, "largest_oriented", (Z, Y, X), np.uint8, chunk)
    up = lambda a, sl: np.repeat(np.repeat(np.repeat(a, cell, 0), cell, 1), cell, 2)[tuple(slice(0, s.stop - s.start) for s in sl)]
    for z0 in range(0, Z, chunk):
        for y0 in range(0, Y, chunk):
            for x0 in range(0, X, chunk):
                sl = (slice(z0, min(z0 + chunk, Z)), slice(y0, min(y0 + chunk, Y)), slice(x0, min(x0 + chunk, X)))
                cs = tuple(slice(s.start // cell, -(-s.stop // cell)) for s in sl)
                nv = np.asarray(normal_unit[(slice(None),) + sl], np.float32)
                csg = up(cellsig[cs], sl); cnn = np.stack([up(cn[cs + (k,)], sl) for k in range(3)])
                agree = np.sign(np.sum(nv * cnn, 0)); agree[agree == 0] = 1
                sg = csg * agree
                sup = (np.asarray(support[sl]) > 0) & (csg != 0)
                no[(slice(None),) + sl] = np.round(np.where(sup, sg, 0) * nv * 127).astype(np.int8)
                so[sl] = sup.astype(np.uint8)
                bo[sl] = (sup & up(cellbig[cs], sl)).astype(np.uint8)
                if po is not None:
                    p = np.asarray(psi[sl], np.float32)
                    ps = np.where(sg > 0, p, (1.0 - p) % 1.0)
                    po[sl] = (np.round(ps * 256) % 256).astype(np.uint8)
    return no, po
