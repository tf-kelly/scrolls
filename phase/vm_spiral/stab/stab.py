"""STAB harness (phase/prereg/STAB.md, hash 2fd55d782ef2). One re-solve per call, through vc_sheet_check's own
build_state/solve (SessA-15 tie-break default); only the edge list and node list change.
Usage: PYTHONPATH=<vc_sheet_check dir> python stab.py EDGES_JSON MODE OUT_NPZ [BAD_IDS]
  MODE: full | a | null_a | jk<i>   (a: drop Stevens-bad nodes; null_a: drop 9,170 random nodes, seed 20260931;
        jk<i>: drop 10 % of joins, seed 20260930+i)
Writes nodes, k, component (re-solve) and the run's metadata.
"""
import json, sys, time
import numpy as np
from vc_sheet_check import solve as SV

EDGES, MODE, OUT = sys.argv[1:4]
E, nodes, xyz, axis_xy, _ = SV.load_edges(EDGES)
nodes = [int(p) for p in nodes]
meta = dict(mode=MODE, n_edges_in=len(E), n_nodes_in=len(nodes))
if MODE in ("a", "null_a"):
    if MODE == "a":
        drop = {int(x) for x in open(sys.argv[4]).read().split()} & set(nodes)
    else:
        n_bad = len({int(x) for x in open(sys.argv[4]).read().split()} & set(nodes))
        drop = set(np.array(nodes)[np.random.default_rng(20260931).permutation(len(nodes))[:n_bad]].tolist())
    nodes = [p for p in nodes if p not in drop]
    E = [e for e in E if e["a"] not in drop and e["b"] not in drop]
    meta.update(dropped_nodes=len(drop))
elif MODE.startswith("jk"):
    i = int(MODE[2:]); m = len(E) // 10
    gone = set(np.random.default_rng(20260930 + i).choice(len(E), size=m, replace=False).tolist())
    E = [e for j, e in enumerate(E) if j not in gone]
    meta.update(dropped_edges=m, seed=20260930 + i)
elif MODE != "full":
    sys.exit(f"unknown mode {MODE}")
t0 = time.time()
st = SV.build_state(E, nodes, xyz, axis_xy, 134.0)
res = SV.solve(st)
meta.update(n_edges=len(E), n_nodes=len(nodes), s_chosen=res["s_chosen"], n_components=res["n_components"],
            n_unsatisfied=res["n_unsatisfied"], wall_s=round(time.time() - t0, 1))
np.savez_compressed(OUT, nodes=np.array(st["nodes"], np.int64), k=np.rint(res["k"]).astype(np.int64),
                    component=np.asarray(res["component"], np.int64), meta=json.dumps(meta))
print(json.dumps(meta), flush=True)
