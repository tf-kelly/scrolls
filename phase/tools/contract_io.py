#!/usr/bin/env python3
"""Shared writers for contract outputs (CONTRACT.md Amendment 4): the full-frame sparse overlay (§4.2 as amended)
and §4.1 clusters. Written for the pinned zarr (phase/tools/requirements.txt: zarr==2.18.7); on-disk format is Zarr v2.

Overlay: one array per scan level l = 0..5, shape = the scan's level shape, 128³ chunks, dimension_separator "/",
uint8, fill 0, blosc lz4 (the configuration VC3D drew in SessD's in-app run), NO translation. Only chunks inside the
overlay region are ever written; all-zero chunks inside it may be omitted. Level l is the 2x max-pool of level l-1 in
absolute scan coordinates.

Overlay region (Amendment 10 §A10.2): the bbox of every evaluated point of every scored pair (PA, PB, midpoints) and
of every vertex the wrong-turn test evaluated, plus the 380 µm halo, snapped outward to the 128 grid
(`overlay_region`). It is reported as `report.json` `overlay_region`, separate from the analysis `region`.
"""
import json
import uuid as _uuid
from pathlib import Path

import numpy as np

# PHerc1667 (Scroll 4) scan 20231117161658: the fixture's scan. Named constants only; no function defaults to them
# (a Scroll 4 default here and in region mode truncated overlay regions of a larger scan). Callers pass the scan
# shape of the run they write for, from its manifest or its CT.
PHERC1667_SCAN_URL = "https://dl.ash2txt.org/full-scrolls/Scroll4/PHerc1667.volpkg/volumes_zarr/20231117161658.zarr"
PHERC1667_SCAN_SHAPE0 = (11174, 3340, 3440)
SCAN_URL = PHERC1667_SCAN_URL                                    # kept for existing imports; PHerc1667 only
CH = 128
VOX_UM = 7.91
CLUSTER_EPS_VOX = 50 / VOX_UM          # §4.1 single linkage at 50 µm
CELL_MM2 = (4 * VOX_UM) ** 2 / 1e6      # one tifxyz cell


def level_shapes(scan_shape0, levels=6):
    """Scan level shapes by ceil-halving from the level-0 shape (as vc_sheet_check.zarrio.level_shapes)."""
    out = [tuple(int(s) for s in scan_shape0)]
    for _ in range(levels - 1):
        out.append(tuple(-(-s // 2) for s in out[-1]))
    return out


SCAN_LEVEL_SHAPES = level_shapes(PHERC1667_SCAN_SHAPE0)          # PHerc1667 only; kept for existing imports


def _scan_shape0(scan_shape):
    if scan_shape is None or len(scan_shape) != 3 or min(int(s) for s in scan_shape) <= 0:
        raise ValueError(f"scan_shape must be the run's level-0 scan shape (z, y, x), got {scan_shape!r}")
    return tuple(int(s) for s in scan_shape)


def snap_region(lo_zyx, hi_zyx, halo_vox, scan_shape):
    """bbox [lo, hi) plus halo, snapped outward to the 128 grid and clipped to the scan -> (origin_zyx, shape_zyx).
    scan_shape: the run's level-0 scan shape (z, y, x); required."""
    scan_shape = _scan_shape0(scan_shape)
    lo = [max(0, int(np.floor((l - halo_vox) / CH)) * CH) for l in lo_zyx]
    hi = [min(s, int(np.ceil((h + halo_vox) / CH)) * CH) for h, s in zip(hi_zyx, scan_shape)]
    return lo, [h - l for l, h in zip(lo, hi)]


def read_axis_file(path):
    """Amendment 12 §A12.1: segment-mode axis file, either format -> (z, y, x) float arrays sorted by z, level-0 voxels.
    - ours: CSV with header z,y,x (phase/tools/axis/*.csv);
    - villa: umbilicus.json {"control_points": [{"z", "y", "x"}, ...]} (SessE-8 `phase/sc/vm/umbilicus.json`);
      a `coordinate_scale` other than 1.0 is refused rather than guessed."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        doc = json.loads(path.read_text())
        if float(doc.get("coordinate_scale", 1.0)) != 1.0:
            raise ValueError(f"{path}: coordinate_scale {doc['coordinate_scale']} != 1.0 is not supported")
        cp = doc["control_points"]
        zyx = np.array([[float(c["z"]), float(c["y"]), float(c["x"])] for c in cp])
    else:
        import csv
        with open(path) as f:
            r = csv.DictReader(f)
            if [h.strip().lower() for h in r.fieldnames] != ["z", "y", "x"]:
                raise ValueError(f"{path}: header must be z,y,x, got {r.fieldnames}")
            zyx = np.array([[float(row["z"]), float(row["y"]), float(row["x"])] for row in r])
    if len(zyx) < 2:
        raise ValueError(f"{path}: need at least 2 axis points")
    zyx = zyx[np.argsort(zyx[:, 0], kind="stable")]
    return zyx[:, 0], zyx[:, 1], zyx[:, 2]


def axis_yx_at(z_query, axis):
    """Axis (y, x) at level-0 z, linear between control points. Returns (y, x, n_outside): queries outside the control
    points' z range are clamped here, whereas villa extrapolates linearly, so callers must report n_outside."""
    z, y, x = axis; zq = np.asarray(z_query, np.float64)
    return np.interp(zq, z, y), np.interp(zq, z, x), int(((zq < z[0]) | (zq > z[-1])).sum())


def _selftest_axis(tmpdir):
    """Both formats of the same axis read identically."""
    tmpdir = Path(tmpdir); src = Path(__file__).resolve().parent / "axis/pherc1667_x3slab2_axis.csv"
    a = read_axis_file(src)
    j = tmpdir / "umbilicus.json"
    j.write_text(json.dumps({"control_points": [dict(z=float(z), y=float(y), x=float(x)) for z, y, x in zip(*a)]}))
    b = read_axis_file(j)
    zq = np.linspace(a[0][0] - 50, a[0][-1] + 50, 97)
    ya, xa, na = axis_yx_at(zq, a); yb, xb, nb = axis_yx_at(zq, b)
    return all(np.array_equal(u, v) for u, v in zip(a, b)) and np.array_equal(ya, yb) and np.array_equal(xa, xb) and na == nb > 0


def overlay_region(point_sets_zyx, scan_shape, halo_um=380.0):
    """Amendment 10 §A10.2: bbox over all given (n, 3) zyx point arrays, plus halo, snapped outward and clipped to the
    run's scan -> (origin, shape). scan_shape: level-0 (z, y, x) of the run's scan; required."""
    P = np.concatenate([np.asarray(p, np.float64).reshape(-1, 3) for p in point_sets_zyx])
    return snap_region(P.min(0), P.max(0) + 1, halo_um / VOX_UM, scan_shape)


def _pool(arr, lo):
    """2x max-pool of a level array covering [lo, lo+shape) in absolute coords -> (pooled, lo_next)."""
    pad_front = [l % 2 for l in lo]
    a = np.pad(arr, [(p, 0) for p in pad_front])
    a = np.pad(a, [(0, s % 2) for s in a.shape])
    s = a.shape
    out = a.reshape(s[0] // 2, 2, s[1] // 2, 2, s[2] // 2, 2).max((1, 3, 5))
    return out, [(l - p) // 2 for l, p in zip(lo, pad_front)]


def write_overlay_fullframe(path, region_arr, origin_zyx, scan_shape0, name="contract overlay", levels=6):
    """region_arr: uint8 level-0 values over [origin, origin + shape). Writes the full-frame sparse OME-Zarr v2 with
    the run's scan shape (scan_shape0, level-0 z, y, x; required)."""
    import numcodecs
    import zarr
    path = Path(path)
    root = zarr.open_group(str(path), mode="w")
    comp = numcodecs.Blosc(cname="lz4", clevel=5, shuffle=numcodecs.Blosc.SHUFFLE)
    arr, lo = np.asarray(region_arr, np.uint8), list(origin_zyx)
    shapes = level_shapes(_scan_shape0(scan_shape0), levels)
    ds = []
    for lv in range(levels):
        if lv > 0:
            arr, lo = _pool(arr, lo)
        shp = shapes[lv]
        hi = [min(l + s, S) for l, s, S in zip(lo, arr.shape, shp)]
        a = root.create_dataset(str(lv), shape=shp, chunks=(CH,) * 3, dtype="u1", compressor=comp, fill_value=0,
                                dimension_separator="/", write_empty_chunks=False)
        a[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]] = arr[:hi[0] - lo[0], :hi[1] - lo[1], :hi[2] - lo[2]]
        ds.append(dict(path=str(lv), coordinateTransformations=[dict(type="scale", scale=[VOX_UM * 2 ** lv] * 3)]))
    root.attrs["multiscales"] = [dict(version="0.4", name=name, axes=[dict(name=c, type="space", unit="micrometer") for c in "zyx"], datasets=ds)]
    root.attrs["contract"] = "v1+A4"
    root.attrs["region"] = dict(origin_zyx=list(map(int, origin_zyx)), shape_zyx=list(map(int, np.asarray(region_arr).shape)))
    json.dump({"type": "vol", "uuid": str(_uuid.uuid5(_uuid.NAMESPACE_URL, str(path.resolve()))), "name": name, "format": "zarr",
               "width": shapes[0][2], "height": shapes[0][1], "slices": shapes[0][0], "voxelsize": VOX_UM},
              open(path / "meta.json", "w"), indent=1)


def single_linkage(points_by_item, eps=CLUSTER_EPS_VOX):
    """points_by_item: {item: (N,3) array}. Items are linked when any of their points are within eps. -> list of item lists."""
    from scipy.spatial import cKDTree
    items = list(points_by_item)
    if not items:
        return []
    P = np.concatenate([np.asarray(points_by_item[i], float) for i in items])
    lab = np.concatenate([np.full(len(points_by_item[i]), n) for n, i in enumerate(items)])
    par = list(range(len(items)))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    for a, b in cKDTree(P).query_pairs(eps):
        ra, rb = find(lab[a]), find(lab[b])
        if ra != rb:
            par[max(ra, rb)] = min(ra, rb)
    groups = {}
    for n, i in enumerate(items):
        groups.setdefault(find(n), []).append(i)
    return sorted(groups.values(), key=lambda g: (-len(g), str(g[0])))


def cluster_record(cid, kind, pts_xyz, patches, pairs, theta_of_xyz, wrap, area_cm2, max_score):
    """§4.1 cluster. pts_xyz are (x, y, z) voxels (tifxyz / X6 convention); stored zyx (Amendment 4 §A4.4)."""
    zyx = np.asarray(pts_xyz, float)[:, ::-1]
    th = theta_of_xyz(np.asarray(pts_xyz, float))
    ks = [wrap[p] for p in patches if p in wrap]
    return dict(id=int(cid), kind=kind, n_pairs=len(pairs), n_patches=len(patches), area_cm2=float(area_cm2),
                centroid_zyx=[round(float(v), 2) for v in zyx.mean(0)],
                bbox_zyx=[[round(float(v), 2) for v in zyx.min(0)], [round(float(v), 2) for v in zyx.max(0)]],
                theta_deg=round(float(np.degrees(np.angle(np.mean(np.exp(1j * th)))) % 360), 3),
                wrap_index_range=[int(min(ks)), int(max(ks))] if ks else None,
                patches=sorted(int(p) for p in patches), pairs=[list(map(int, k)) for k in sorted(pairs)],
                max_risk=None if max_score is None else float(max_score))
