"""H1 step (5), swap test: our LP synchronizer, as a standalone, reusable module.

Copied verbatim from phase/x7/x7_v9.py's "shared LP machinery" section (build_lp, lp_synchronise,
gauge_fix, anchors_per_component) -- v9 is frozen (phase/OWNERS.md) and is not edited; this is a new
file so the solver can be called on winding-sync's own constraints without re-executing all of v9's
measurement construction.

Term convention (matches v9): a term is (a, b, d, w) meaning d ~ k_b - k_a, weight w.
Winding-sync's convention (winding_sync/solver.py) is the mirror: delta ~ w_i - w_j for edge (i, j).
Callers translate between the two explicitly (see run_swap_test.py) rather than this module guessing.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.csgraph import connected_components


def anchors_per_component(terms, n_nodes):
    ii = np.array([t[0] for t in terms])
    jj = np.array([t[1] for t in terms])
    A = coo_matrix((np.ones(len(terms)), (ii, jj)), shape=(n_nodes, n_nodes))
    A = A + A.T
    ncomp, lab = connected_components(A, directed=False)
    anchor = {}
    for i in range(n_nodes):
        c = lab[i]
        if c not in anchor or i < anchor[c][0]:
            anchor[c] = (i, i)
    return lab, {i for i, _ in anchor.values()}


def build_lp(terms, n_nodes, fixed_bounds=None):
    lab, anchor_idxs = anchors_per_component(terms, n_nodes)
    M = len(terms)
    n_vars = n_nodes + M
    rows, cols, data, b_ub = [], [], [], []
    for e, (a, b, d, w) in enumerate(terms):
        r = len(b_ub)
        rows += [r, r, r]; cols += [b, a, n_nodes + e]; data += [1, -1, -1]; b_ub.append(d)
        r2 = len(b_ub)
        rows += [r2, r2, r2]; cols += [b, a, n_nodes + e]; data += [-1, 1, -1]; b_ub.append(-d)
    A_ub = csr_matrix((data, (rows, cols)), shape=(2 * M, n_vars))
    b_ub = np.array(b_ub, float)
    c = np.zeros(n_vars); c[n_nodes:] = [w for (_, _, _, w) in terms]
    bounds = [(None, None)] * n_nodes + [(0, None)] * M
    for i in anchor_idxs:
        bounds[i] = (0, 0)
    if fixed_bounds:
        for i, lo, hi in fixed_bounds:
            bounds[i] = (lo, hi)
    return c, A_ub, b_ub, bounds, lab


def lp_synchronise(terms, n_nodes, fixed_bounds=None):
    c, A_ub, b_ub, bounds, lab = build_lp(terms, n_nodes, fixed_bounds)
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
    if res.status != 0:
        return None, lab, None
    k = np.round(res.x[:n_nodes]).astype(int)
    return k, lab, res.fun
