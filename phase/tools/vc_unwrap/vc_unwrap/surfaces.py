"""Stage 4, surfaces: one tifxyz per winding from the fitted checkpoint, with villa's own reconstruction
(flatten_spiral_checkpoint._build_model and the winding loop of its _export_source_surface, villa f4570bf), written by
villa's tifxyz.save_tifxyz instead of being combined and flattened. Each winding's grid is (z step) x (theta step) at
`--step` voxels; vertices outside the fit's z range or outside the scan volume are -1 (villa's convention).
Winding indices are the fit's own. The table surfaces/windings.csv gives, for each winding, the modal wrap number of
our solved index among patch vertices within 4 voxels of it, so the two numberings can be compared; it is a diagnostic,
not a relabelling."""
import csv, json, sys
from collections import Counter
from pathlib import Path

import numpy as np


def run_surfaces(out, villa, scan_shape, step=None, device=None, chunk=200_000):  # scan_shape required (item-159)
    villa = Path(villa); sys.path.insert(0, str(villa))
    import torch
    from checkpoint_io import load_checkpoint_cpu
    import flatten_spiral_checkpoint as FS
    from sample_spiral import get_spiral_yxs
    from tifxyz import save_tifxyz
    dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    ck = load_checkpoint_cpu(str(out / "fit/run/checkpoint_fitted.ckpt"))
    cfg = FS._checkpoint_config(ck) if hasattr(FS, "_checkpoint_config") else ck["config"]
    model = FS._build_model(ck, cfg, out / "dataset/umbilicus.json", dev)
    tr, drpw = model.get_slice_to_spiral_transform(), model.get_dr_per_winding()
    zb, ze = int(ck["z_begin"]), int(ck["z_end"]); st = int(step or FS._value(cfg, "step_size", 20))
    first = int(ck.get("preview_first_winding", FS._value(cfg, "first_winding", 10)))
    last = int(cfg.get("shell_outer_winding_idx") if cfg.get("shell_outer_winding_idx") is not None else int(cfg["model_gap_expander_num_windings"]) - 1)
    yxs = get_spiral_yxs(last + 1, drpw, st, group_by_winding=True, device=str(dev))
    zs = torch.arange(zb, ze, st, dtype=torch.float32, device=dev)
    sd = out / "surfaces"; sd.mkdir(parents=True, exist_ok=True); rows = []
    tree, kv = _patch_index(out)
    with torch.inference_mode():
        for w in range(first, last + 1):
            sp = torch.cat([zs[:, None, None].expand(-1, yxs[w].shape[0], 1), yxs[w][None].expand(zs.shape[0], -1, 2)], -1)
            flat = sp.reshape(-1, 3)
            g = torch.cat([tr.inv(flat[i:i + chunk]).cpu() for i in range(0, len(flat), chunk)]).reshape_as(sp).numpy().astype(np.float32)
            g[(g[..., 0] < zb) | (g[..., 0] >= ze)] = -1.0
            outside = ((g < 0) | (g >= np.asarray(scan_shape, np.float32))).any(-1)      # extrapolated past the scan
            g[outside] = -1.0
            valid = (g != -1).any(-1)
            if not valid.any():
                continue
            name = f"winding_{w:03d}"
            save_tifxyz(g, str(sd), name, st, 7.91, "vc-unwrap (villa flatten_spiral_checkpoint reconstruction)")
            if tree is not None:
                d, j = tree.query(g[valid][:, ::-1], distance_upper_bound=4.0); hit = np.isfinite(d)
                k = Counter(kv[j[hit]].tolist()).most_common(1)
            else:
                hit, k = np.zeros(0, bool), []
            rows.append(dict(winding=w, surface=name, valid_vertices=int(valid.sum()), near_patch_vertices=int(hit.sum()),
                             modal_wrap_index=(k[0][0] if k else ""), modal_share=(round(k[0][1] / max(int(hit.sum()), 1), 3) if k else "")))
    with open(sd / "windings.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["winding"]); wr.writeheader(); wr.writerows(rows)
    return dict(windings_written=len(rows), step=st, z_range=[zb, ze], first=first, last=last)


def _patch_index(out):
    """KD-tree over exported patch vertices (x, y, z) with each patch's solved wrap number."""
    from PIL import Image
    from scipy.spatial import cKDTree
    if not (out / "dataset/verified_patches").is_dir() or not (out / "check/wrap_index.csv").exists():
        return None, None
    k = {int(r["patch"]): int(r["k_q3c"]) for r in csv.DictReader(open(out / "check/wrap_index.csv"))}
    pts, kv = [], []
    for d in (out / "dataset/verified_patches").iterdir():
        if int(d.name) not in k:
            continue
        X = np.array(Image.open(d / "x.tif")); Y = np.array(Image.open(d / "y.tif")); Z = np.array(Image.open(d / "z.tif"))
        m = (X > 0) & (Z > 0) & np.isfinite(X); p = np.stack([X[m], Y[m], Z[m]], -1)[::4]
        pts.append(p); kv.append(np.full(len(p), int(k[int(d.name)])))
    P = np.concatenate(pts); return cKDTree(P), np.concatenate([np.concatenate(kv), [-999]])


if __name__ == "__main__":      # run under villa's interpreter: python -m vc_unwrap.surfaces OUT VILLA STEP|- Z Y X
    o, v, stp = Path(sys.argv[1]), sys.argv[2], (None if sys.argv[3] == "-" else int(sys.argv[3]))
    res = run_surfaces(o, v, step=stp, scan_shape=tuple(int(x) for x in sys.argv[4:7]))
    (o / "surfaces/SURFACES_RECORD.json").write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res))
