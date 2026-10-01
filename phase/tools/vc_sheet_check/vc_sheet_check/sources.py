"""Inputs: CT, patches, tables. All coordinates here are scan L0 voxels.

CT sources (read at a pyramid level, box given as z,y,x at that level):
  - http(s) OME-Zarr / zarr pyramid (the public scan): vendored switchwitness Volume,
    unmodified; missing chunks read as 0 and are reported, never treated as dark papyrus.
  - a local OME-Zarr crop with a `translation` (the fixture's ct.zarr): read in
    place; voxels outside the crop are 0 and counted as missing.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

VOX_UM = 7.91
SCROLL4_URL = "https://dl.ash2txt.org/full-scrolls/Scroll4/PHerc1667.volpkg/volumes_zarr/20231117161658.zarr"
SCROLL1_URL = ("https://dl.ash2txt.org/full-scrolls/Scroll1/PHercParis4.volpkg/volumes_zarr_standardized/"
               "54keV_7.91um_Scroll1A.zarr")


class CT:
    def __init__(self, spec, level):
        self.spec, self.level = str(spec), level
        self.http = self.spec.startswith("http")
        if self.http:
            from ._vendor.switchwitness_core import Volume
            self.vol = Volume(self.spec, level)
            self.vol0 = Volume(self.spec, 0)
            self.shape0 = list(self.vol0.shape)
            self.origin_l0 = [0, 0, 0]
            self.extent_l0 = self.shape0
        else:
            import zarr
            p = Path(self.spec)
            attrs = json.loads((p / ".zattrs").read_text())
            ds = attrs["multiscales"][0]["datasets"]
            tr0 = [t for t in ds[0]["coordinateTransformations"] if t["type"] == "translation"]
            sc0 = [t for t in ds[0]["coordinateTransformations"] if t["type"] == "scale"][0]["scale"]
            vox = float(sc0[0])
            self.origin_l0 = [int(round(v / vox)) for v in tr0[0]["translation"]] if tr0 else [0, 0, 0]
            self.arr = zarr.open_array(str(p / ds[level]["path"]), mode="r")
            a0 = zarr.open_array(str(p / ds[0]["path"]), mode="r")
            self.extent_l0 = list(a0.shape)
            self.shape0 = None                     # full scan shape unknown from a crop

    def read(self, lo, hi):
        """lo/hi: z,y,x at self.level. Returns (array, info)."""
        if self.http:
            return self.vol.read(lo, hi)
        s = 2 ** self.level
        o = [v // s for v in self.origin_l0]
        out = np.zeros([b - a for a, b in zip(lo, hi)], self.arr.dtype)
        src_lo = [max(a - oo, 0) for a, oo in zip(lo, o)]
        src_hi = [min(b - oo, n) for b, oo, n in zip(hi, o, self.arr.shape)]
        if all(b > a for a, b in zip(src_lo, src_hi)):
            dst = tuple(slice(a + oo - l, b + oo - l) for a, b, oo, l in zip(src_lo, src_hi, o, lo))
            out[dst] = self.arr[tuple(slice(a, b) for a, b in zip(src_lo, src_hi))]
        covered = int(np.prod([max(b - a, 0) for a, b in zip(src_lo, src_hi)]))
        return out, dict(local=self.spec, covered_frac=covered / max(out.size, 1))

    def coverage_box_l0(self):
        return self.origin_l0, [a + b for a, b in zip(self.origin_l0, self.extent_l0)]


def load_patches(sources, ids=None):
    """-> {id: grid (h, w, 3) float64 L0 x,y,z with NaN holes}, {id: (source, member, kind)}.
    Accepts zips or directories of Stevens-layout patch_N/ tifxyz folders or pipeline9 .bin files
    (vendored switchwitness list_sources/read_patch, unmodified)."""
    from ._vendor.switchwitness_core import list_sources, read_patch
    G, where = {}, {}
    for pid, src, mem, kind in list_sources(sources):
        if ids is not None and pid not in ids:
            continue
        G[pid] = read_patch(src, mem, kind).astype(np.float64); where[pid] = (src, mem, kind)
    return G, where


def patch_table(G, labels=None):
    """Rows in phase/x1/patches.csv's layout (bbox and centroid in x, y, z order)."""
    rows = []
    for pid in sorted(G):
        v = G[pid][np.isfinite(G[pid]).all(-1)]
        if not len(v):
            continue
        lo, hi, c = v.min(0), v.max(0), v.mean(0)
        rows.append(dict(id=pid, label=(labels or {}).get(pid, "unknown"), n=len(v), h=G[pid].shape[0], w=G[pid].shape[1],
                         xmin=lo[0], xmax=hi[0], ymin=lo[1], ymax=hi[1], zmin=lo[2], zmax=hi[2], cx=c[0], cy=c[1], cz=c[2]))
    return rows


def read_table(path):
    return list(csv.DictReader(open(path)))


def patches_meeting(rows, origin_zyx, shape_zyx):
    z0, y0, x0 = origin_zyx; z1, y1, x1 = [a + b for a, b in zip(origin_zyx, shape_zyx)]
    return sorted(int(r["id"]) for r in rows
                  if float(r["xmax"]) >= x0 and float(r["xmin"]) < x1 and float(r["ymax"]) >= y0 and float(r["ymin"]) < y1
                  and float(r["zmax"]) >= z0 and float(r["zmin"]) < z1)
