"""SessE-8c: loader-aware constraint filter (PROTOCOL.md amendment 10). Runs AFTER snap_anchors.py.

Rule L: drop every collection naming a patch villa would not load for the fit's z-range (villa's load_one:
        z prefilter -> erosion keeps >= 1 valid quad -> a remaining valid vertex in z range).
Rule T' (amendments 11-12), RELATIVE role only: drop every relative collection where, both patches loading, a point's partner is at villa projection
        distance <= own + EPS (EPS = 0.01 vox). Near-coincident surfaces resolve toward the partner under villa's
        C++ surface index (SessB) but not under brute force, so exact ties are backend-dependent. Candidates:
        partner eroded valid-quad vertex within RADIUS = 1.0 vox; confirmed with villa's own Patch.project.
Rewrites both role files of each dataset root (root and spiral/ copies) and the Amendment 2 manifest.
Usage: python loader_filter.py VILLA_SRC Z_BEGIN Z_END DATASET_ROOT [DATASET_ROOT ...]"""
import hashlib, json, sys
from pathlib import Path

import numpy as np
import scipy.ndimage
from PIL import Image
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parents[1]
VILLA, ZB, ZE, ROOTS = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), [Path(r) for r in sys.argv[4:]]
FILES = ("same_windings.json", "relative_windings.json")
EPS, RADIUS = 0.01, 1.0


def load_state(d):
    """Villa's load decision for one patch directory; returns (loaded, eroded valid mask, zyx)."""
    meta = json.load(open(d / "meta.json"))
    z = np.array(Image.open(d / "z.tif")).astype(np.float32)
    mask = None
    if (d / "mask.tif").exists():
        mask = np.array(Image.open(d / "mask.tif")); mask = mask[..., 0] if mask.ndim == 3 else mask
    inr = (z >= ZB) & (z < ZE)
    if mask is not None:
        inr &= mask != 0
    if not inr.any():
        return False, None, None, "z ROI prefilter"
    zyx = np.stack([z, np.array(Image.open(d / "y.tif")), np.array(Image.open(d / "x.tif"))], -1).astype(np.float32)
    if mask is not None:
        zyx[mask == 0] = -1.0
    valid = np.any(zyx != -1, axis=-1)
    cells = int(meta["spiral_patch_erode_cells"]) if meta.get("spiral_patch_erode_cells") is not None else 1
    if cells > 0:
        er = scipy.ndimage.binary_erosion(valid, iterations=cells, border_value=0)
        if (valid & ~er).any():
            zyx[valid & ~er] = -1.0
            valid = np.any(zyx != -1, axis=-1)
            q = valid[:-1, :-1] & valid[1:, :-1] & valid[:-1, 1:] & valid[1:, 1:]
            if not q.any():
                return False, None, None, "erosion"
    zs = zyx[valid][:, 0]
    if not ((zs >= ZB) & (zs < ZE)).any():
        return False, None, None, "z ROI after erosion"
    return True, valid, zyx, None


def main():
    pdir = (ROOTS[0] / "verified_patches").resolve()
    state, reason = {}, {}
    for d in sorted(pdir.iterdir(), key=lambda x: int(x.name)):
        ok, valid, zyx, why = load_state(d)
        state[d.name] = (valid, zyx) if ok else None
        if not ok:
            reason[d.name] = why
    unloaded = sorted(reason, key=int)
    trees = {}

    def tree(pid):
        if pid not in trees:
            valid, zyx = state[pid]
            q = valid[:-1, :-1] & valid[1:, :-1] & valid[:-1, 1:] & valid[1:, 1:]
            corner = np.zeros_like(valid)
            for di, dj in ((0, 0), (1, 0), (0, 1), (1, 1)):
                corner[di:di + q.shape[0], dj:dj + q.shape[1]] |= q
            trees[pid] = cKDTree(zyx[corner])
        return trees[pid]

    # villa's own projection for tie confirmation
    sys.path.insert(0, str(VILLA))
    import torch  # noqa: E402
    from tifxyz import load_tifxyz  # noqa: E402
    torch.set_num_threads(1)
    SRC = (VILLA / "spiral_helpers.py").read_text(); i = SRC.index("def erode_patch_valid_region"); j = SRC.index("\ndef ", i + 10)
    ns = {"scipy": scipy, "np": np, "torch": torch}; exec(SRC[i:j], ns)
    vpatch = {}

    def villa_patch(pid):
        if pid not in vpatch:
            pt = load_tifxyz(str(pdir / pid), z_range=(ZB, ZE)); c = pt.erosion_cells(1)
            if c > 0:
                ns["erode_patch_valid_region"](pt, c)
            vpatch[pid] = pt
        return vpatch[pid]

    def dist(pid, p_xyz):
        return np.float32(float(villa_patch(pid).project(torch.tensor(p_xyz[::-1], dtype=torch.float32))[1]))

    report = dict(z_range=[ZB, ZE], unloaded_patches=unloaded, unloaded_reasons={r: sum(1 for v in reason.values() if v == r) for r in set(reason.values())},
                  arms={})
    for root in ROOTS:
        arm = dict()
        for fn in FILES:
            f = root / fn
            doc = json.load(open(f)); cols = doc["collections"]
            drop_L, drop_T, cands, tied_points = [], [], 0, 0
            for cid, c in cols.items():
                a, b = c["name"][len("between_patches__"):].split("__")
                if state.get(a) is None or state.get(b) is None:
                    drop_L.append(cid); continue
                pts = [pt for _, pt in sorted(c["points"].items(), key=lambda kv: int(kv[0]))]
                tie = False
                if fn == "same_windings.json":      # amendment 12: same-winding ties kept (trivially satisfied)
                    continue
                for own, partner, p in ((a, b, pts[0]["p"]), (b, a, pts[1]["p"])):
                    x = np.array(p[::-1], float)
                    if tree(partner).query(x)[0] > RADIUS:
                        continue
                    cands += 1
                    d_own, d_par = dist(own, p), dist(partner, p)
                    if d_par <= d_own + EPS:
                        tie = True
                        tied_points += 1
                if tie:
                    drop_T.append(cid)
            for cid in drop_L + drop_T:
                del cols[cid]
            raw = json.dumps(doc, separators=(",", ":")).encode()
            (root / fn).write_bytes(raw); (root / "spiral" / fn).write_bytes(raw)
            arm[fn] = dict(dropped_unloaded=len(drop_L), dropped_tie=len(drop_T), tied_points=tied_points, tie_candidates_checked=cands, kept=len(cols),
                           tie_collections=[cols_name for cols_name in drop_T], sha256=hashlib.sha256(raw).hexdigest())
        env_f = root / "spiral_constraints.json"
        env = json.load(open(env_f))
        for c in env["constraints"]:
            fn = Path(c["file"]).name; c["sha256"] = arm[fn]["sha256"]; c["collections"] = arm[fn]["kept"]
        env["loader_filter"] = dict(rule="PROTOCOL.md amendments 10-12 (L: unloaded patch, both roles; T-prime on relative only: partner within own + 0.01 vox; same-winding ties kept)", z_range=[ZB, ZE], n_unloaded_patches=len(unloaded))
        env_f.write_text(json.dumps(env, indent=1) + "\n")
        report["arms"][root.name] = arm
    (HERE / "results/sc8c_loader_filter.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "unloaded_patches"}, indent=1)); print("unloaded:", len(unloaded))


if __name__ == "__main__":
    main()
