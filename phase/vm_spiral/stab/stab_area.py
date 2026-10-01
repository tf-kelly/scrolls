"""Per-patch surface area of tranche_s4_whole patches (STAB.md §2): each valid 2x2 quad of the tifxyz grid counts
0.5*|d1 x d2| (d1, d2 its diagonals), voxel^2 -> cm^2 at 7.91 um. Streams dataset.tgz once.
Usage: python stab_area.py DATASET_TGZ OUT_JSON"""
import io, json, sys, tarfile
import numpy as np, tifffile
tgz, out = sys.argv[1:3]; CM2 = (7.91e-4) ** 2; area, buf = {}, {}
with tarfile.open(tgz, "r|gz") as tf:
    for mem in tf:
        if not mem.isfile(): continue
        parts = mem.name.split("/"); fn = parts[-1]
        if fn not in ("x.tif", "y.tif", "z.tif") or not parts[-2].isdigit(): continue
        buf.setdefault(parts[-2], {})[fn[0]] = tifffile.imread(io.BytesIO(tf.extractfile(mem).read())).astype(np.float64)
        if len(buf[parts[-2]]) < 3: continue
        B = buf.pop(parts[-2]); P = np.stack([B["x"], B["y"], B["z"]], -1)
        ok = (P[..., 0] > 0) & (P[..., 2] > 0) & np.isfinite(P).all(-1)
        q = ok[:-1, :-1] & ok[1:, 1:] & ok[:-1, 1:] & ok[1:, :-1]
        d1 = P[1:, 1:] - P[:-1, :-1]; d2 = P[:-1, 1:] - P[1:, :-1]
        a = 0.5 * np.linalg.norm(np.cross(d1, d2), axis=-1)
        area[parts[-2]] = float(a[q].sum() * CM2)
json.dump(area, open(out, "w")); print(len(area), sum(area.values()))
