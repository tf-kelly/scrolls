"""Sheet-separation regime per patch quad, from the dataset's own relative-winding pairs.

A relative_windings.json collection named between_patches__A__B holds two points on
different windings; its separation is |p1 - p2| * voxel_um (the anchor-pair definition
used by the slab studies). Each pair is attached to both patches A and B. A quad of a patch
takes the regime of the nearest attached anchor within `radius` voxels (both anchors of a
pair, Euclidean, quad centre to anchor), else 'none'. Regimes: '<25', '25-50', '>=50' um.

This depends only on the dataset (never on a fit), so arm (a) and arm (b) are split by the
same quad labels.
"""
import json
import os
import re
from collections import defaultdict

import numpy as np
from scipy.spatial import cKDTree

REGIMES = ('<25', '25-50', '>=50', 'none')
EDGES_UM = (25.0, 50.0)


def regime_code(sep_um):
    s = np.asarray(sep_um, np.float64)
    return np.where(s < EDGES_UM[0], 0, np.where(s < EDGES_UM[1], 1, 2)).astype(np.int8)


def load_relative_pairs(path, voxel_um):
    """-> dict patch_id(str) -> (anchors_zyx (M,3), sep_um (M,)) and a summary."""
    with open(path) as f:
        cols = json.load(f)['collections']
    by_patch = defaultdict(lambda: ([], []))
    seps, bad = [], 0
    pat = re.compile(r'between_patches__(.+?)__(.+)$')
    for c in cols.values():
        m = pat.match(c.get('name', ''))
        pts = sorted(c['points'].items(), key=lambda kv: int(kv[0]))
        if not m or len(pts) != 2:
            bad += 1
            continue
        p1 = np.array(pts[0][1]['p'], np.float64)[::-1]   # x,y,z -> z,y,x
        p2 = np.array(pts[1][1]['p'], np.float64)[::-1]
        sep = float(np.linalg.norm(p1 - p2) * voxel_um)
        seps.append(sep)
        for pid in m.groups():
            a, s = by_patch[pid]
            a.extend([p1, p2])
            s.extend([sep, sep])
    out = {k: (np.array(v[0]), np.array(v[1])) for k, v in by_patch.items()}
    seps = np.array(seps)
    summ = dict(pairs=int(len(seps)), unparsed=bad, patches_with_pairs=len(out),
                pairs_by_regime={r: int((regime_code(seps) == i).sum()) for i, r in enumerate(REGIMES[:3])},
                sep_um_quantiles={q: float(np.percentile(seps, q)) for q in (5, 25, 50, 75, 95)} if len(seps) else {})
    return out, summ


def quad_regimes(quad_centres_zyx, anchors, radius):
    """quad_centres (H-1,W-1,3) with NaN for invalid -> int8 codes (H-1,W-1): 0,1,2 regime, 3 none, -1 invalid."""
    q = quad_centres_zyx.reshape(-1, 3)
    ok = np.isfinite(q).all(1)
    out = np.full(len(q), -1, np.int8)
    out[ok] = 3
    if anchors is not None and len(anchors[0]) and ok.any():
        tree = cKDTree(anchors[0])
        d, i = tree.query(q[ok], k=1, distance_upper_bound=radius)
        hit = np.isfinite(d)
        codes = np.full(ok.sum(), 3, np.int8)
        codes[hit] = regime_code(anchors[1][i[hit]])
        out[ok] = codes
    return out.reshape(quad_centres_zyx.shape[:2])
