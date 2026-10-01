"""Minimal zarr v2 chunk reader (HTTP or local directory) with a disk cache.

Only chunks that a caller touches are fetched. A chunk that is absent on the server
(HTTP 404, or a missing local file) is *unavailable*: its samples come back NaN, never
as dark papyrus. Arrays may be stored in any axis order; `axes` names the stored order
(e.g. 'yxz') and every public call takes and returns z, y, x.
"""
import json
import os
import threading
import time
from collections import OrderedDict

import numpy as np

try:
    import numcodecs
except ImportError:  # pragma: no cover
    numcodecs = None


class ZarrArray:
    def __init__(self, url, axes='zyx', cache_dir=None, mem_chunks=256, retries=6, mem_mb=None):
        self.url = url.rstrip('/')
        self.remote = self.url.startswith(('http://', 'https://'))
        self.axes = axes
        self.perm = [axes.index(a) for a in 'zyx']      # stored axis for each of z,y,x
        self.cache_dir = cache_dir
        self.retries = retries
        self._mem = OrderedDict()
        self._mem_max = mem_chunks
        # byte budget for decoded/haloed chunks (per process); env VC_SCALE_CACHE_MB overrides
        self._mem_bytes_max = int((mem_mb or float(os.environ.get('VC_SCALE_CACHE_MB', '1536'))) * 2 ** 20)
        self._mem_bytes = 0
        self._lock = threading.Lock()
        self._session = None
        self.stats = {'fetched': 0, 'missing': 0, 'bytes': 0, 'cache_hits': 0}
        meta = json.loads(self._read('.zarray'))
        if meta.get('zarr_format') != 2:
            raise ValueError(f'{url}: only zarr v2 arrays are supported')
        self.dtype = np.dtype(meta['dtype'])
        self.order = meta.get('order', 'C')
        self.sep = meta.get('dimension_separator', '.')
        self.fill = meta.get('fill_value') or 0
        comp = meta.get('compressor')
        self.codec = numcodecs.get_codec(comp) if comp else None
        self.filters = [numcodecs.get_codec(f) for f in (meta.get('filters') or [])]
        st_shape, st_chunks = meta['shape'], meta['chunks']
        self.shape = tuple(st_shape[p] for p in self.perm)     # z, y, x
        self.chunks = tuple(st_chunks[p] for p in self.perm)

    # --- raw IO ----------------------------------------------------------------------------
    def _http(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def _read(self, key):
        """Bytes for key, or None if absent. Remote reads retry transient errors."""
        if not self.remote:
            p = os.path.join(self.url, key)
            if not os.path.exists(p):
                return None
            with open(p, 'rb') as f:
                return f.read()
        if self.cache_dir:
            cp = os.path.join(self.cache_dir, key.replace('/', '_'))
            if os.path.exists(cp):
                self.stats['cache_hits'] += 1
                with open(cp, 'rb') as f:
                    data = f.read()
                return None if data == b'__MISSING__' else data
        delay = 2.0
        for attempt in range(self.retries):
            try:
                r = self._http().get(f'{self.url}/{key}', timeout=120)
                if r.status_code == 404:
                    data = None
                    break
                r.raise_for_status()
                data = r.content
                break
            except Exception:
                if attempt == self.retries - 1:
                    raise
                time.sleep(delay)
                delay *= 2
        if self.cache_dir:
            os.makedirs(self.cache_dir, exist_ok=True)
            cp = os.path.join(self.cache_dir, key.replace('/', '_'))
            tmp = f'{cp}.{os.getpid()}.{threading.get_ident()}.tmp'
            with open(tmp, 'wb') as f:
                f.write(b'__MISSING__' if data is None else data)
            os.replace(tmp, cp)
        return data

    def prefetch(self, keys, workers=16):
        """Fetch chunk keys (cz,cy,cx) into the disk cache concurrently (no decode)."""
        from concurrent.futures import ThreadPoolExecutor
        def one(k):
            st_idx = [0, 0, 0]
            for i, p in enumerate(self.perm):
                st_idx[p] = k[i]
            self._read(self.sep.join(str(i) for i in st_idx))
        with ThreadPoolExecutor(workers) as ex:
            list(ex.map(one, keys))

    # --- sampling --------------------------------------------------------------------------
    def chunk_keys_for(self, zyx, margin=1.0):
        """Set of chunk keys needed to trilinearly sample points zyx (N,3) (+ margin)."""
        keys = set()
        z = np.asarray(zyx, np.float64)
        ok = np.isfinite(z).all(1)
        z = z[ok]
        for off in (-margin, margin + 1):
            for oy in (-margin, margin + 1):
                for ox in (-margin, margin + 1):
                    p = np.floor(z + np.array([off, oy, ox])).astype(np.int64)
                    c = p // np.array(self.chunks)
                    inb = ((c >= 0) & (c < -(-np.array(self.shape) // np.array(self.chunks)))).all(1)
                    keys.update(map(tuple, np.unique(c[inb], axis=0).tolist()))
        return keys

    def _put(self, key, arr):
        nb = 0 if arr is None else arr.nbytes
        with self._lock:
            if key in self._mem:
                return
            self._mem[key] = arr
            self._mem_bytes += nb
            while self._mem and (self._mem_bytes > self._mem_bytes_max or len(self._mem) > self._mem_max):
                _, old = self._mem.popitem(last=False)
                self._mem_bytes -= 0 if old is None else old.nbytes

    def halo(self, cz, cy, cx):
        """Chunk (cz,cy,cx) plus one voxel of its +z/+y/+x neighbours, as float32 (or float16
        for 8-bit data), NaN where unavailable; None if the chunk itself is unavailable.
        Every trilinear sample whose base voxel lies in the chunk reads only this array."""
        key = ('h', cz, cy, cx)
        with self._lock:
            if key in self._mem:
                self._mem.move_to_end(key)
                return self._mem[key]
        core = self._raw_chunk(cz, cy, cx)
        if core is None:
            h = None
        else:
            ch = self.chunks
            dt = np.float16 if self.dtype.itemsize == 1 else np.float32
            h = np.full((ch[0] + 1, ch[1] + 1, ch[2] + 1), np.nan, dt)
            h[:ch[0], :ch[1], :ch[2]] = core
            for dz, dy, dx in ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1)):
                nb = self._raw_chunk(cz + dz, cy + dy, cx + dx)
                if nb is None:
                    continue
                sz = slice(ch[0], ch[0] + 1) if dz else slice(0, ch[0])
                sy = slice(ch[1], ch[1] + 1) if dy else slice(0, ch[1])
                sx = slice(ch[2], ch[2] + 1) if dx else slice(0, ch[2])
                h[sz, sy, sx] = nb[(slice(0, 1) if dz else slice(None)),
                                   (slice(0, 1) if dy else slice(None)),
                                   (slice(0, 1) if dx else slice(None))]
        self._put(key, h)
        return h

    def _raw_chunk(self, cz, cy, cx):
        """Decoded chunk in native dtype (z,y,x), or None; small raw LRU."""
        nch = -(-np.array(self.shape) // np.array(self.chunks))
        if min(cz, cy, cx) < 0 or cz >= nch[0] or cy >= nch[1] or cx >= nch[2]:
            return None
        key = ('r', cz, cy, cx)
        with self._lock:
            if key in self._mem:
                self._mem.move_to_end(key)
                return self._mem[key]
        st_idx = [0, 0, 0]
        for i, p in enumerate(self.perm):
            st_idx[p] = (cz, cy, cx)[i]
        raw = self._read(self.sep.join(str(i) for i in st_idx))
        if raw is None:
            arr = None
            self.stats['missing'] += 1
        else:
            self.stats['fetched'] += 1
            self.stats['bytes'] += len(raw)
            buf = self.codec.decode(raw) if self.codec else raw
            for f in reversed(self.filters):
                buf = f.decode(buf)
            st_chunks = [0, 0, 0]
            for i, p in enumerate(self.perm):
                st_chunks[p] = self.chunks[i]
            a = np.frombuffer(buf, self.dtype).reshape(st_chunks, order=self.order)
            inv = [self.axes.index(a_) for a_ in 'zyx']
            arr = np.ascontiguousarray(a.transpose(inv))
        self._put(key, arr)
        return arr

    def sample(self, zyx):
        """Trilinear samples at points zyx (N,3) in this array's voxel frame.
        Returns float32 (N,) with NaN where any interpolation neighbour is unavailable
        (outside the array, in a missing chunk, or a non-finite point)."""
        zyx = np.asarray(zyx, np.float64).reshape(-1, 3)
        out = np.full(len(zyx), np.nan, np.float32)
        ok = np.isfinite(zyx).all(1)
        shp = np.array(self.shape)
        ok[ok] &= ((zyx[ok] >= 0).all(1) & (zyx[ok] < shp - 1).all(1))
        if not ok.any():
            return out
        idx = np.nonzero(ok)[0]
        p = zyx[idx]
        b = np.floor(p).astype(np.int64)
        f = (p - b).astype(np.float32)
        ch = np.array(self.chunks)
        c = b // ch
        r = b - c * ch
        ck = (c[:, 0] << 42) + (c[:, 1] << 21) + c[:, 2]
        order = np.argsort(ck, kind='stable')
        cks, starts = np.unique(ck[order], return_index=True)
        ends = np.append(starts[1:], len(order))
        acc = np.full(len(idx), np.nan, np.float32)
        for s_, e_ in zip(starts, ends):
            sel = order[s_:e_]
            cz, cy, cx = (int(v) for v in c[sel[0]])
            h = self.halo(cz, cy, cx)
            if h is None:
                continue
            rz, ry, rx = r[sel, 0], r[sel, 1], r[sel, 2]
            fz, fy, fx = f[sel, 0], f[sel, 1], f[sel, 2]
            gz, gy, gx = 1 - fz, 1 - fy, 1 - fx
            v = (h[rz, ry, rx] * (gz * gy * gx) + h[rz, ry, rx + 1] * (gz * gy * fx)
                 + h[rz, ry + 1, rx] * (gz * fy * gx) + h[rz, ry + 1, rx + 1] * (gz * fy * fx)
                 + h[rz + 1, ry, rx] * (fz * gy * gx) + h[rz + 1, ry, rx + 1] * (fz * gy * fx)
                 + h[rz + 1, ry + 1, rx] * (fz * fy * gx) + h[rz + 1, ry + 1, rx + 1] * (fz * fy * fx))
            acc[sel] = v
        out[idx] = acc
        return out


def open_level(url, level=None, axes='zyx', cache_dir=None, mem_chunks=256):
    """Open an OME-zarr level ('<url>/<level>') or a bare array (level None)."""
    u = url.rstrip('/') + (f'/{level}' if level is not None else '')
    cd = None if cache_dir is None else os.path.join(cache_dir, f'L{level if level is not None else "x"}')
    return ZarrArray(u, axes=axes, cache_dir=cd, mem_chunks=mem_chunks)
