"""P3 extension, POST HOC (COORD 04:25 item 2; not in the 81e18d6 pre-registration): the same measures and bands
as p3_fold.py, along page 1's remaining boundary under the sheet-unwrapped key q' (the pieces decks 2-3 sample:
smoothed-q' boundary pieces >= 50 edge points, excluding points within 25 cells of edges where q' changes with w
unchanged). All pieces pooled as one band; control = each piece's polyline shifted 25 cells to each side.
  p3_p1r.py PAGES_DIR D1_MAIN_JSON DUMP_DIR OUT_JSON"""
import json, sys
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
from scipy.stats import fisher_exact
pages, d1p, dump, outp = sys.argv[1:5]
src = open("phase/review/stevens/p3/p3_fold.py").read()
G = {}; exec(src[src.index("import json"):src.index("out = {")].replace("pages, d1p, outp = sys.argv[1:4]", f"pages, d1p = {pages!r}, {d1p!r}"), G)
b2 = open("phase/review/stevens/bdeck2/build_bdeck2.py").read()
H2 = {"np": np, "ndimage": ndimage, "cKDTree": cKDTree, "dump": dump}
for name in ("def smoothed_S", "def edges", "def keys", "def chain"):
    a = b2.index(name); b = b2.index("\ndef ", a + 5); exec(b2[a:b], H2)
a = b2.index("def unk_pieces"); b = b2.index("\ndef ", a + 5); exec(b2[a:b], H2)
valid, F = G["flags"](1); H, W = valid.shape
pcs, nres = H2["unk_pieces"](valid)
allB = np.zeros((H, W), bool)
for Q in json.load(open(d1p))["pages"][[p["page"] for p in json.load(open(d1p))["pages"]].index(1)]["polylines_rowcol"]: allB |= G["raster_band"](Q, H, W)
band = np.zeros((H, W), bool); ctrl = np.zeros((H, W), bool)
for Q in pcs: allB |= G["raster_band"](Q, H, W)
for Q in pcs:
    band |= G["raster_band"](Q, H, W)
    tg = np.array([Q[min(j + 2, len(Q) - 1)] - Q[max(j - 2, 0)] for j in range(len(Q))]); tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-9
    nrm = np.stack([-tg[:, 1], tg[:, 0]], 1)
    for sg in (-1, 1): ctrl |= G["raster_band"](Q + sg * 25 * nrm, H, W)
band &= valid; dropped = int((ctrl & valid & allB).sum()); ctrl &= valid & ~allB
rec = {"post_hoc": True, "page": 1, "group": "P1R (remaining boundary, q')", "pieces": len(pcs), "residual_edges_excluded": nres,
       "band_cells": int(band.sum()), "control_cells": int(ctrl.sum()), "control_cells_dropped_near_boundary": dropped, "rates": {}}
for name, Fm in F.items():
    b, c = int((Fm & band).sum()), int((Fm & ctrl).sum())
    rec["rates"][name] = {"band": [b, int(band.sum()), round(b / max(band.sum(), 1), 5)], "control": [c, int(ctrl.sum()), round(c / max(ctrl.sum(), 1), 5)]}
a = rec["rates"]["any"]; rb, rc = a["band"][2], a["control"][2]
p = fisher_exact([[a["band"][0], a["band"][1] - a["band"][0]], [a["control"][0], a["control"][1] - a["control"][0]]], alternative="greater")[1]
rec["fisher_p_any"] = float(p); rec["elevated_by_p3_rule"] = bool(rb >= 2 * rc and (rb - rc) >= 0.005 and p < 0.01)
json.dump(rec, open(outp, "w"), indent=1); print(json.dumps(rec))
