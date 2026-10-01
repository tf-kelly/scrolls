"""Tiny JSON-RPC client for VC3D's agent bridge (newline-delimited JSON over a Unix socket)."""
import json, socket, sys, time

class Bridge:
    def __init__(self, path, timeout=60):
        for _ in range(120):
            try:
                self.s = socket.socket(socket.AF_UNIX); self.s.connect(path); break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError("bridge socket not up: " + path)
        self.s.settimeout(timeout); self.f = self.s.makefile("rwb"); self.n = 0

    def call(self, method, **params):
        self.n += 1
        self.f.write((json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params}) + "\n").encode()); self.f.flush()
        while True:
            msg = json.loads(self.f.readline())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg["result"]
