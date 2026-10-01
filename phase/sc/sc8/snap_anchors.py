"""SessE-8 fix for the name-check failure: snap each constraint point onto its OWN patch's eroded surface.

Cause (sc8_name_check.json diagnosis): X6 anchors lie in overlap regions near patch edges. villa erodes every
patch by 1 cell (4 voxels at scale 0.25) at load (spiral_helpers.erode_patch_valid_region). That strips the
anchor's own surface, so the between_patches rule ("nearest of the named pair within 2.5 voxels") hands it to
the partner.
Fix: replace each point by the nearest vertex of a valid quad of its own patch AFTER villa's erosion (villa's rules at
a92521b: valid = any(zyx != -1); erosion = scipy binary_erosion(border_value=0, iterations=erosion_cells);
erosion_cells = meta.json spiral_patch_erode_cells or 1). No constraint is dropped; Δ is unchanged.
Rewrites both role files of each given dataset root in place (and spiral/ copies), and writes displacement stats.
Usage: python snap_anchors.py DATASET_ROOT [DATASET_ROOT ...]"""
import hashlib, json, sys
from pathlib import Path

import numpy as np
import scipy.ndimage
from PIL import Image
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parents[1]


def eroded_vertices(d):
    meta = json.load(open(d / "meta.json"))
    zyx = np.stack([np.array(Image.open(d / f"{c}.tif")) for c in "zyx"], -1).astype(np.float32)
    if (d / "mask.tif").exists():
        m = np.array(Image.open(d / "mask.tif")); m = m[..., 0] if m.ndim == 3 else m; zyx[m == 0] = -1.0
    valid = np.any(zyx != -1, axis=-1)
    cells = int(meta["spiral_patch_erode_cells"]) if meta.get("spiral_patch_erode_cells") is not None else 1
    if cells > 0:
        valid = scipy.ndimage.binary_erosion(valid, iterations=cells, border_value=0)
    q = valid[:-1, :-1] & valid[1:, :-1] & valid[:-1, 1:] & valid[1:, 1:]
    corner = np.zeros_like(valid)
    for di, dj in ((0, 0), (1, 0), (0, 1), (1, 1)):
        corner[di:di + q.shape[0], dj:dj + q.shape[1]] |= q
    return zyx[corner]                                              # (N, 3) z, y, x


def main():
    roots = [Path(r) for r in sys.argv[1:]]
    patch_dir = roots[0] / "verified_patches"
    docs = {r: {fn: json.load(open(r / fn)) for fn in ("same_windings.json", "relative_windings.json") if (r / fn).exists()} for r in roots}
    need = {}
    for r, dd in docs.items():
        for fn, doc in dd.items():
            for cid, c in doc["collections"].items():
                a, b = c["name"][len("between_patches__"):].split("__")
                for pid, (k, pt) in zip((a, b), sorted(c["points"].items(), key=lambda kv: int(kv[0]))):
                    need.setdefault(pid, []).append((r, fn, cid, k))
    moves, empty = [], 0
    for pid, refs in need.items():
        v = eroded_vertices(patch_dir / pid)
        if len(v) == 0:
            empty += 1; continue
        tree = cKDTree(v)
        for r, fn, cid, k in refs:
            pt = docs[r][fn]["collections"][cid]["points"][k]
            d, i = tree.query(np.array(pt["p"][::-1], float))
            z, y, x = v[i]; pt["p"] = [float(x), float(y), float(z)]; moves.append(d)
    out = {}
    for r, dd in docs.items():
        for fn, doc in dd.items():
            raw = json.dumps(doc, separators=(",", ":")).encode()
            (r / fn).write_bytes(raw); (r / "spiral" / fn).write_bytes(raw)
            out[f"{r.name}/{fn}"] = hashlib.sha256(raw).hexdigest()
        env_f = r / "spiral_constraints.json"                  # keep the Amendment 2 manifest's hashes in step with the snapped files
        if env_f.exists():
            env = json.load(open(env_f))
            for c in env["constraints"]:
                c["sha256"] = out[f"{r.name}/{Path(c['file']).name}"]
            env["anchors"] = "snapped to own eroded patch (sc8/snap_anchors.py)"
            env_f.write_text(json.dumps(env, indent=1) + "\n")
    m = np.array(moves)
    res = dict(points_snapped=int(len(m)), patches_with_no_eroded_quads=empty,
               displacement_vox=dict(median=float(np.median(m)), p90=float(np.percentile(m, 90)), max=float(m.max()),
                                     share_gt_2p5=float((m > 2.5).mean())), files_sha256=out)
    (HERE / "results/sc8_snap.json").write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
