"""Zarr v2 array writing that works under zarr-python 2.x and 3.x.

phase/requirements.txt pins zarr<3, but phase/tools/example_outputs.py uses the
zarr 3 API; the integration machine may have either, so both are supported.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def _major():
    import zarr
    return int(zarr.__version__.split(".")[0])


def open_group(path):
    import zarr
    if _major() >= 3:
        return zarr.open_group(str(path), mode="w", zarr_format=2)
    return zarr.open_group(str(path), mode="w")


def write_array(root_path, name, data, chunks=(128, 128, 128), separator="/"):
    """Dense array root_path/name (zarr v2, given chunk key separator); zero chunks are not stored."""
    data = np.asarray(data)
    return write_sparse_array(root_path, name, data.shape, [((0, 0, 0), data)], dtype=data.dtype,
                              chunks=chunks, separator=separator)


def write_sparse_array(root_path, name, shape, blocks, dtype=np.uint8, chunks=(128, 128, 128), separator="/"):
    """Full-frame array of `shape` holding only `blocks` [(origin_zyx, array)];
    chunks never written read back as fill_value 0."""
    import zarr
    from numcodecs import Blosc
    comp = Blosc(cname="zstd", clevel=3, shuffle=Blosc.NOSHUFFLE)
    path = f"{root_path}/{name}"
    if _major() >= 3:
        g = zarr.open_group(str(root_path), mode="a", zarr_format=2)
        a = g.create_array(name, shape=tuple(int(s) for s in shape), dtype=dtype, chunks=chunks, fill_value=0,
                           chunk_key_encoding={"name": "v2", "separator": separator}, compressors=comp,
                           config={"write_empty_chunks": False})
    else:
        a = zarr.open_array(path, mode="w", shape=tuple(int(s) for s in shape), dtype=dtype, chunks=chunks,
                            fill_value=0, dimension_separator=separator, write_empty_chunks=False, compressor=comp)
    for o, blk in blocks:
        o = np.asarray(o, int); hi = np.minimum(o + blk.shape, shape); lo = np.maximum(o, 0)
        if (hi <= lo).any():
            continue
        src = tuple(slice(int(l - oo), int(h - oo)) for l, h, oo in zip(lo, hi, o))
        a[tuple(slice(int(l), int(h)) for l, h in zip(lo, hi))] = blk[src]
    return a


def put_attrs(group, attrs):
    for k, v in attrs.items():
        group.attrs[k] = v


# ------------------------------------------------------------------------------------------------ Amendment 4 overlay

def level_shapes(scan_shape0, levels=6):
    """Scan level shapes by ceil-halving (equals contract_io.SCAN_LEVEL_SHAPES for PHerc1667)."""
    out = [tuple(int(s) for s in scan_shape0)]
    for _ in range(levels - 1):
        out.append(tuple(-(-s // 2) for s in out[-1]))
    return out


def write_overlay_fullframe_sparse(path, blocks0, scan_shape0, region_origin, region_shape, name="vc_sheet_check overlay",
                                   levels=6, extra_attrs=None):
    """Amendment 4 §A4.1 overlay (the format of phase/tools/contract_io.write_overlay_fullframe), written chunk by chunk
    so a large region never has to exist as one array.

    blocks0: {(cz, cy, cx): uint8 (128,128,128)} level-0 chunks (chunk-grid indices) holding nonzero values; chunks
    outside the region must not be passed. Level l+1 is the 2x max-pool of level l in absolute coordinates: since
    chunks are 128-aligned (even), each parent chunk is built from its 8 children's pooled 64^3 octants.
    Zarr v2 on disk, chunks 128^3, '/', uint8, fill 0, blosc-lz4 clevel 5 shuffle 1, no translation, VC3D meta.json."""
    import numcodecs
    import uuid as _uuid
    CH = 128
    shapes = level_shapes(scan_shape0, levels)
    comp = numcodecs.Blosc(cname="lz4", clevel=5, shuffle=numcodecs.Blosc.SHUFFLE)
    path = Path(path); root = open_group(path); ds = []
    blocks = {k: np.asarray(v, np.uint8) for k, v in blocks0.items() if np.any(v)}
    for lv in range(levels):
        if lv > 0:
            parents = {}
            for (cz, cy, cx), b in blocks.items():
                p = parents.setdefault((cz // 2, cy // 2, cx // 2), np.zeros((CH,) * 3, np.uint8))
                pooled = b.reshape(64, 2, 64, 2, 64, 2).max((1, 3, 5))
                oz, oy, ox = (cz % 2) * 64, (cy % 2) * 64, (cx % 2) * 64
                np.maximum(p[oz:oz + 64, oy:oy + 64, ox:ox + 64], pooled, out=p[oz:oz + 64, oy:oy + 64, ox:ox + 64])
            blocks = {k: v for k, v in parents.items() if np.any(v)}
        shp = shapes[lv]
        a = _create(root, path, str(lv), shp, comp)
        for (cz, cy, cx), b in blocks.items():
            lo = (cz * CH, cy * CH, cx * CH); hi = [min(l + CH, s) for l, s in zip(lo, shp)]
            a[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]] = b[:hi[0] - lo[0], :hi[1] - lo[1], :hi[2] - lo[2]]
        ds.append(dict(path=str(lv), coordinateTransformations=[dict(type="scale", scale=[7.91 * 2 ** lv] * 3)]))
    attrs = dict(multiscales=[dict(version="0.4", name=name, axes=[dict(name=c, type="space", unit="micrometer") for c in "zyx"],
                                   datasets=ds)], contract="v1+A4",
                 region=dict(origin_zyx=list(map(int, region_origin)), shape_zyx=list(map(int, region_shape))))
    attrs.update(extra_attrs or {})
    put_attrs(root, attrs)
    json.dump({"type": "vol", "uuid": str(_uuid.uuid5(_uuid.NAMESPACE_URL, str(path.resolve()))), "name": name, "format": "zarr",
               "width": shapes[0][2], "height": shapes[0][1], "slices": shapes[0][0], "voxelsize": 7.91},
              open(path / "meta.json", "w"), indent=1)


def _create(root, path, name, shape, comp):
    import zarr
    if _major() >= 3:
        return root.create_array(name, shape=shape, dtype="u1", chunks=(128,) * 3, fill_value=0, compressors=comp,
                                 chunk_key_encoding={"name": "v2", "separator": "/"}, config={"write_empty_chunks": False})
    return zarr.open_array(str(Path(path) / name), mode="w", shape=shape, dtype="u1", chunks=(128,) * 3, fill_value=0,
                           dimension_separator="/", write_empty_chunks=False, compressor=comp)


def region_to_blocks(arr, origin):
    """A dense level-0 region array (origin 128-aligned) -> {chunk index: 128^3 block} of nonzero chunks."""
    CH = 128; arr = np.asarray(arr, np.uint8); out = {}
    for z in range(0, arr.shape[0], CH):
        for y in range(0, arr.shape[1], CH):
            for x in range(0, arr.shape[2], CH):
                sub = arr[z:z + CH, y:y + CH, x:x + CH]
                if sub.any():
                    b = np.zeros((CH,) * 3, np.uint8); b[:sub.shape[0], :sub.shape[1], :sub.shape[2]] = sub
                    out[((origin[0] + z) // CH, (origin[1] + y) // CH, (origin[2] + x) // CH)] = b
    return out


def spheres_to_blocks(points_zyx, radius, value, region_origin, region_shape, blocks=None):
    """Rasterise 'every voxel within `radius` voxels of a point' (voxel centres, as example_outputs.py) into chunk
    blocks, clipped to the region. points_zyx: (N, 3) L0 voxel coordinates."""
    CH = 128; blocks = {} if blocks is None else blocks
    ro = np.asarray(region_origin); re_ = ro + np.asarray(region_shape)
    for c in np.asarray(points_zyx, float):
        lo = np.maximum(np.floor(c - radius).astype(int), ro); hi = np.minimum(np.ceil(c + radius).astype(int) + 1, re_)
        if np.any(lo >= hi):
            continue
        g = np.stack(np.meshgrid(*[np.arange(a, b) for a, b in zip(lo, hi)], indexing="ij"), -1)
        inside = np.linalg.norm(g + 0.5 - c, axis=-1) <= radius
        for (zz, yy, xx) in np.argwhere(inside) + lo:
            k = (zz // CH, yy // CH, xx // CH); b = blocks.get(k)
            if b is None:
                b = blocks[k] = np.zeros((CH,) * 3, np.uint8)
            b[zz % CH, yy % CH, xx % CH] = max(b[zz % CH, yy % CH, xx % CH], value)
    return blocks
