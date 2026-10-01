#!/usr/bin/env python3
"""Sheet check through VC3D's agent bridge. DEVELOPMENT AND TEST HARNESS, not a user deliverable (see ../README.md:
the bridge is off by default, its protocol is not declared stable, and focus/detach are not available as API).

Runs vc_sheet_check on the active segment and current volume of a running VC3D (started with
--agent-bridge), attaches the overlay as VC3D's overlay volume, centres the slice views on the first
cluster, and prints the other clusters. All analysis stays in the checker.

Usage: sheet_check_bridge.py [--socket PATH] [--checker PROG] [--segment DIR] [--volume DIR] [--out DIR]
Exit codes: 0 ok; 2 checker failed or report invalid; 3 overlay not loaded (clusters still printed);
4 bridge unavailable or incompatible.
Limits (see README): no dock or menu; the project file gains one entry per run (the bridge has no call to
remove a volume entry); jump-to uses two ctrl-clicks (GUI focus semantics, not a documented focus call).
"""
import argparse, glob, json, os, shutil, socket, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sheet_check_core as core

PROTOCOL = 2
TAG = "sheet_check"


class BridgeError(RuntimeError):
    pass


class Bridge:
    def __init__(self, path, timeout=120):
        self.s = socket.socket(socket.AF_UNIX)
        self.s.connect(path)
        self.s.settimeout(timeout)
        self.f = self.s.makefile("rwb")
        self.n = 0

    def call(self, method, **params):
        self.n += 1
        msg = {"jsonrpc": "2.0", "id": self.n, "method": method, "params": params}
        self.f.write((json.dumps(msg) + "\n").encode()); self.f.flush()
        while True:
            line = self.f.readline()
            if not line:
                raise BridgeError("bridge closed the connection")
            r = json.loads(line)
            if r.get("id") == self.n:
                if "error" in r:
                    raise BridgeError(f"{method}: {r['error']}")
                return r["result"]


def discover_socket():
    """Newest live record in ~/.vc3d/agent_bridge/ (SPEC 'Activation and discovery')."""
    best = None
    for f in glob.glob(os.path.expanduser("~/.vc3d/agent_bridge/*.json")):
        try:
            rec = json.load(open(f)); os.kill(int(rec["pid"]), 0)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        path, started = rec.get("path"), rec.get("startedAt", 0)
        if path and (best is None or started > best[0]):
            best = (started, path)
    return best[1] if best else None


def jump(b, xyz):
    """Move the focus POI to xyz: ctrl-click in the xy plane viewer (sets x, y), then in the yz viewer
    (sets y, z). canvas.click only accepts points on the viewer's current plane, hence two steps."""
    viewers = {v["surfName"]: v["viewerId"] for v in b.call("state.get")["viewers"]}
    xy, yz = viewers.get("xy plane"), viewers.get("seg yz")
    if not xy or not yz:
        raise BridgeError(f"xy/yz plane viewers not found: {sorted(viewers)}")
    x, y, z = xyz
    zc = b.call("state.get")["focusPoi"]["position"]["z"]
    p1 = {"x": x, "y": y, "z": zc}
    b.call("viewer.center_on_point", viewer=xy, point=p1)
    b.call("canvas.click", viewer=xy, position=p1, modifiers=["ctrl"])
    p2 = {"x": x, "y": y, "z": z}
    b.call("viewer.center_on_point", viewer=yz, point=p2)
    b.call("canvas.click", viewer=yz, position=p2, modifiers=["ctrl"])
    f = b.call("state.get")["focusPoi"]["position"]
    return [f["x"], f["y"], f["z"]]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--socket"); ap.add_argument("--checker"); ap.add_argument("--segment")
    ap.add_argument("--volume"); ap.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        path = a.socket or discover_socket()
        if not path:
            raise BridgeError("no live VC3D agent bridge found; start VC3D with --agent-bridge")
        b = Bridge(path)
        ping = b.call("ping")
        if ping.get("protocolVersion") != PROTOCOL:
            raise BridgeError(f"bridge protocol {ping.get('protocolVersion')}, this script speaks {PROTOCOL}")
        st = b.call("state.get")
        volume = a.volume or (st.get("volume") or {}).get("path")
        segment = a.segment
        if not segment:
            act = [s for s in b.call("segments.list").get("segments", []) if s.get("active")]
            segment = act[0]["path"] if act else None
        if not segment or not volume:
            raise BridgeError("select a segment and load a volume first (or pass --segment/--volume)")
    except (OSError, BridgeError) as e:
        print(f"error: {e}", file=sys.stderr); return 4

    checker = a.checker or os.environ.get("VC_SHEET_CHECK") or shutil.which("vc_sheet_check")
    if not checker:
        print("error: vc_sheet_check not found (PATH or VC_SHEET_CHECK)", file=sys.stderr); return 2
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + f"{int(time.time() * 1000) % 1000:03d}"
    out = a.out or os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                                "vc3d-sheet-check", f"{os.path.basename(segment.rstrip('/'))}-{stamp}")
    os.makedirs(out, exist_ok=True)
    argv_ = core.build_argv(checker, segment, volume, out)
    print("run:", " ".join(argv_), file=sys.stderr)
    rc = subprocess.run(argv_).returncode
    if rc != 0:  # A4.2: non-zero exit is failure whatever files exist
        try:
            detail = json.load(open(os.path.join(out, "report.json"))).get("error", "")
        except (OSError, ValueError):
            detail = ""
        print(f"error: vc_sheet_check exited with code {rc}" + (f": {detail}" if detail else ""), file=sys.stderr)
        return 2
    try:
        rep = core.parse_report(open(os.path.join(out, "report.json")).read())
    except (OSError, core.ReportError) as e:
        print(f"error: {e}", file=sys.stderr); return 2

    code = 0
    overlay = core.choose_overlay(out)
    problem = core.overlay_placement_problem(overlay) if overlay else "no overlay.zarr written"
    if problem:
        print(f"error: overlay not loaded: {problem}", file=sys.stderr); code = 3
    else:
        try:
            seg_id = (st.get("activeSurface") or {}).get("id", "")
            before = set(b.call("volume.list")["volumeIds"])
            b.call("volume.attach", location=overlay, tags=[TAG, f"sheet_check_segment:{seg_id}"])
            vid = None
            for _ in range(60):  # volume.attach loads asynchronously
                new = set(b.call("volume.list")["volumeIds"]) - before
                if new:
                    vid = sorted(new)[0]; break
                time.sleep(0.5)
            if not vid:
                raise BridgeError("overlay volume did not appear after volume.attach")
            b.call("viewer.set_overlay", volumeId=vid, colormap="fire", opacity=0.6, window={"low": 0.5, "high": 2.0})
            print(f"overlay: {vid}", file=sys.stderr)
        except BridgeError as e:
            print(f"error: overlay not loaded: {e}", file=sys.stderr); code = 3

    cl = rep["clusters"]
    print(f"clusters: {len(cl)}  pairs_flagged: {rep['pairs_flagged']}  report: {os.path.join(out, 'report.json')}")
    if cl:
        target = core.to_vc3d_xyz(cl[0]["centroid_zyx"])
        try:
            got = jump(b, target)
            print(f"centred on {core.describe_in(rep, cl[0])}  focus xyz={got[0]:g},{got[1]:g},{got[2]:g}")
        except BridgeError as e:
            print(f"error: could not centre on the first cluster: {e}", file=sys.stderr); code = code or 3
        for c in cl[1:]:
            print(core.describe_in(rep, c))
    return code


if __name__ == "__main__":
    sys.exit(main())
