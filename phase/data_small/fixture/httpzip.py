"""Read members of a remote zip with HTTP range requests (no full download). Used by build_fixture.py."""
import io
import urllib.request


class HTTPRangeFile(io.RawIOBase):
    def __init__(self, url, block=1 << 20):
        self.url, self.pos, self.block, self.cache = url, 0, block, {}
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=60) as r:
            self.size = int(r.headers["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def _blk(self, i):
        if i not in self.cache:
            lo = i * self.block; hi = min(lo + self.block, self.size) - 1
            req = urllib.request.Request(self.url, headers={"Range": f"bytes={lo}-{hi}"})
            for attempt in range(5):
                try:
                    with urllib.request.urlopen(req, timeout=120) as r:
                        self.cache[i] = r.read(); break
                except Exception:
                    if attempt == 4:
                        raise
            if len(self.cache) > 256:
                self.cache.pop(next(iter(self.cache)))
        return self.cache[i]

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        out = bytearray()
        while n > 0 and self.pos < self.size:
            i, o = divmod(self.pos, self.block); b = self._blk(i)[o:o + n]
            out += b; self.pos += len(b); n -= len(b)
        return bytes(out)

    def readinto(self, b):
        d = self.read(len(b)); b[:len(d)] = d; return len(d)
