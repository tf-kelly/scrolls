"""The solve's L1 LP as a min-cost circulation, with the contract tie-break (project owner, 2026-09-28; SessA-15).

Primary LP (our_solver.build_lp): minimise sum_e w_e |k_b - k_a - d_e|, integer d, integer w.
Its dual is a circulation: maximise sum d_e y_e, B^T y = 0, |y_e| <= w_e. Solved with OR-Tools SimpleMinCostFlow
(f = y + w on arc a->b, f in [0, 2w], unit cost -d). k is recovered as node potentials from the complementary-
slackness difference constraints (y < w  =>  k_a <= k_b - d ;  y > -w  =>  k_b <= k_a + d) by a vectorised
Bellman-Ford from a virtual source.

Tie-break (SessA-15): minimise primary + eps * sum_i |k_i - r_i|, eps = 1 / (4 M), M = the number of primary terms.
Implemented exactly in integers: primary weights x 4M, plus one weight-1 edge v0 -> i with target r_i per node, where
v0 is a virtual anchor node with k_v0 = 0. The primary optimum is checked, not assumed, to be unchanged.
"""
from __future__ import annotations

import numpy as np


def _solve(a, b, d, w, n_nodes):
    from ortools.graph.python import min_cost_flow
    mcf = min_cost_flow.SimpleMinCostFlow()
    mcf.add_arcs_with_capacity_and_unit_cost(a, b, 2 * w, -d)
    sup = np.zeros(n_nodes, np.int64); np.add.at(sup, a, w); np.subtract.at(sup, b, w)
    mcf.set_nodes_supplies(np.arange(n_nodes), sup)
    st = mcf.solve()
    if st != mcf.OPTIMAL:
        raise RuntimeError(f"min-cost flow status {st}")
    y = mcf.flows(np.arange(len(a))) - w
    lo, hi = y < w, y > -w
    U = np.concatenate([b[lo], a[hi]]); V = np.concatenate([a[lo], b[hi]]); C = np.concatenate([-d[lo], d[hi]])
    k = np.zeros(n_nodes, np.int64); it = 0
    while True:
        cand = k.copy(); np.minimum.at(cand, V, k[U] + C); it += 1
        if np.array_equal(cand, k):
            break
        k = cand
        if it > n_nodes + 1:
            raise RuntimeError("negative cycle in the potential graph: flow not optimal")
    return k, float((d * y).sum()), it


def arrays(terms):
    a = np.array([t[0] for t in terms], np.int64); b = np.array([t[1] for t in terms], np.int64)
    d = np.array([t[2] for t in terms], np.int64); w = np.array([t[3] for t in terms], float)
    if not (np.all(w == np.round(w)) and np.all(w > 0)):
        raise ValueError("the circulation needs positive integer weights (uniform weights: 1)")
    return a, b, d, w.astype(np.int64)


def primary(k, a, b, d, w):
    return float((w * np.abs(k[b] - k[a] - d)).sum())


def solve_plain(terms, n_nodes):
    """Plain L1 optimum: (k gauged so each component's smallest index is 0, component labels, optimal objective)."""
    from ._vendor import our_solver as OS
    lab, _ = OS.anchors_per_component(terms, n_nodes)
    a, b, d, w = arrays(terms)
    k, dual, _ = _solve(a, b, d, w, n_nodes)
    for c in np.unique(lab):
        m = lab == c; k[m] -= k[np.where(m)[0].min()]
    obj = primary(k, a, b, d, w)
    if abs(obj - dual) > 1e-6:
        raise RuntimeError(f"plain circulation: primal {obj} != dual {dual}")
    return k, lab, obj


def solve_tiebreak(terms, n_nodes, r, plain_obj=None):
    """Tie-broken optimum: minimise primary + (1/4M) sum |k_i - r_i| (r: integer per node). Returns (k, labels, primary
    objective, info). k is relative to the virtual anchor (k_v0 = 0); no per-component re-gauging."""
    from ._vendor import our_solver as OS
    lab, _ = OS.anchors_per_component(terms, n_nodes)
    a, b, d, w = arrays(terms); M = len(terms); S = 4 * M
    r = np.asarray(r, np.int64); v0 = n_nodes; nodes = np.arange(n_nodes, dtype=np.int64)
    A = np.concatenate([a, np.full(n_nodes, v0)]); B = np.concatenate([b, nodes])
    D = np.concatenate([d, r]); W = np.concatenate([S * w, np.ones(n_nodes, np.int64)])
    kk, dual, it = _solve(A, B, D, W, n_nodes + 1)
    k = kk[:n_nodes] - kk[v0]
    obj = primary(k, a, b, d, w); tie = float(np.abs(k - r).sum())
    scaled = S * obj + tie
    if abs(scaled - dual) > 1e-6:
        raise RuntimeError(f"tie-break circulation: primal {scaled} != dual {dual}")
    if plain_obj is None:
        plain_obj = solve_plain(terms, n_nodes)[2]
    if abs(obj - plain_obj) > 1e-9:
        raise RuntimeError(f"tie-break changed the primary optimum: {obj} vs {plain_obj}")
    return k, lab, obj, dict(eps=1.0 / S, M=M, tie_term=tie, primary_plain=plain_obj, primary_unchanged=True, bf_iters=it)
