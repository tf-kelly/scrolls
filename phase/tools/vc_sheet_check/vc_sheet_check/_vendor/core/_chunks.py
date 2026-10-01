"""Chunk iteration with halos, and ndarray/zarr output handling.

A "block" is a core region of at most `chunk` voxels per axis plus `halo`
voxels on each side.  Halos that fall outside the volume are filled by
reflection.  Outputs are written core-only, so results do not depend on the
chunking except through the halo width.
"""
from __future__ import annotations

import itertools
import os

import numpy as np


def as_tuple(chunk, ndim=3):
    if np.isscalar(chunk):
        return (int(chunk),) * ndim
    return tuple(int(c) for c in chunk)


def spatial_shape(a):
    return tuple(a.shape[-3:])


def iter_cores(shape, chunk):
    chunk = as_tuple(chunk)
    ranges = [range(0, s, c) for s, c in zip(shape, chunk)]
    for starts in itertools.product(*ranges):
        yield tuple(slice(s, min(s + c, n)) for s, c, n in zip(starts, chunk, shape))


def read_block(a, core, halo, mode="reflect", lo_only=False, hi_only=False):
    """Read core + halo from a (…, z, y, x) array (zarr or ndarray) as float32
    ndarray.  Returns (block, inner) where block[..., inner] is the core."""
    shape = spatial_shape(a)
    halo = as_tuple(halo)
    rd, pad, inner = [], [], []
    for sl, h, n in zip(core, halo, shape):
        hl = 0 if hi_only else h
        hh = 0 if lo_only else h
        s0, s1 = sl.start - hl, sl.stop + hh
        r0, r1 = max(s0, 0), min(s1, n)
        rd.append(slice(r0, r1))
        pad.append((r0 - s0, s1 - r1))
        inner.append(slice(hl, hl + sl.stop - sl.start))
    lead = (slice(None),) * (a.ndim - 3)
    blk = np.asarray(a[lead + tuple(rd)])
    if any(p != (0, 0) for p in pad):
        blk = np.pad(blk, [(0, 0)] * (a.ndim - 3) + pad, mode=mode)
    return blk, tuple(inner)


def make_out(out, name, shape, dtype=np.float32, chunk=128):
    """Allocate an output array: ndarray if out is None, else a zarr array at
    <out>/<name> (Blosc-zstd, bitshuffle), chunked like the processing."""
    if out is None:
        return np.zeros(shape, dtype=dtype)
    import zarr
    from numcodecs import Blosc
    ch = as_tuple(chunk)
    zch = tuple(shape[:-3]) + tuple(min(c, s) for c, s in zip(ch, shape[-3:]))
    return zarr.open_array(os.path.join(str(out), name), mode="w", shape=shape,
                           chunks=zch, dtype=dtype,
                           compressor=Blosc(cname="zstd", clevel=3, shuffle=Blosc.BITSHUFFLE))


def curve_rows(c, zsl):
    """c(z) rows for a z-slice as float32 (n, 2)."""
    return np.asarray(c[zsl], dtype=np.float32)


def theta_r(c, core):
    """theta and r on a core block, from the central curve c(z)."""
    zsl, ysl, xsl = core
    cc = curve_rows(c, zsl)
    y = np.arange(ysl.start, ysl.stop, dtype=np.float32)[None, :, None]
    x = np.arange(xsl.start, xsl.stop, dtype=np.float32)[None, None, :]
    dy = y - cc[:, 0][:, None, None]
    dx = x - cc[:, 1][:, None, None]
    return np.arctan2(dy, dx), np.hypot(dy, dx), dy, dx
