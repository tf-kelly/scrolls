"""F2 page-5 masked deck (BUILD_NOTES.md allocation): 28 boundary frames (P5B) + 12 plain controls (P5C) on Stevens'
page 5, rendered with deck 3's functions unchanged (masked middle, visibility filter, window).
  build_p5deck.py PAGES_DIR D1_MAIN_JSON DUMP_DIR KEY1 KEY2 KEY3 DECK_OUT SEALED_DIR
"""
import hashlib, json, os, secrets, sys
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
HERE = os.path.dirname(os.path.abspath(__file__)); B3 = os.path.join(HERE, "..", "stevens", "bdeck3", "build_bdeck3.py")
pages, d1p, dump, key1, key2, key3, out, sealed = sys.argv[1:9]
src = open(B3).read(); src = src[:src.index("# ---- plan for boundary groups")]
G = {"__file__": B3}; sys.argv = [B3, pages, d1p, dump, key1, key2, "/nonexistent", out, sealed]
exec(compile(src, "build_bdeck3_head", "exec"), G)
np_ = np; rng = np.random.default_rng(20260930 + 5); G["rng"] = rng
xyz = np.array([it["xyz"] for kf in (key1, key2, key3) for it in json.load(open(kf))["items"]]); G["T1"] = cKDTree(xyz)   # decks 1-3
Pg = G["load"](5); P, ok = Pg[0], Pg[1]
pieces = [np.array(pl, float) for pl in [q for q in json.load(open(d1p))["pages"] if q["page"] == 5][0]["polylines_rowcol"]]
L = [G["arclen"](Q)[-1] for Q in pieces]; order = np.argsort(L)[::-1]; items = []; REJ = {"boundary": 0, "control": 0}


def try_at(Q, sv, pc):
    s = G["arclen"](Q); j = min(int(np.searchsorted(s, sv)), len(Q) - 1); tg = Q[min(j + 2, len(Q) - 1)] - Q[max(j - 2, 0)]; tg /= np.linalg.norm(tg) + 1e-9
    r, c = int(round(Q[j, 0])), int(round(Q[j, 1])); g = np.array([-tg[1], tg[0]])
    if not (0 <= r < ok.shape[0] and 0 <= c < ok.shape[1]) or not ok[r, c] or not np.isfinite(Pg[4][r, c]).all(): return None
    if not G["far_from_deck1"](P[r, c]) or not G["line_ok"](ok, r, c, g): return None
    if any(np.hypot(r - it["rowcol"][0], c - it["rowcol"][1]) < G["SEP"] for it in items): return None
    img, segs, x = G["render"](Pg, r, c, g)
    if not G["visible_ok"](segs): REJ["boundary"] += 1; return None
    return {"group": "P5B", "page": 5, "piece": int(pc), "arc_frac": round(float(sv / s[-1]), 3), "rowcol": [r, c], "dir_rowcol": np.round(g, 4).tolist(), "xyz": x, "img": img, "segs": segs}


for pc in order[:8]:
    Q = pieces[pc]; Ltot = L[pc]
    for f in (0.25, 0.5, 0.75):
        got = None
        for d in sorted(np.arange(-10, 10.5, 0.5), key=abs):
            sv = f * Ltot + d
            if 1 <= sv <= Ltot - 1 and (got := try_at(Q, sv, pc)): break
        if got: items.append(got)
        print("P5B piece", pc, f, bool(got), flush=True)
rest = order[8:]; w = np.array([L[p] for p in rest]); need = 28 - len(items); tries = 0
while need > 0 and tries < 5000:
    tries += 1; pc = rest[rng.choice(len(rest), p=w / w.sum())]; sv = rng.uniform(1, L[pc] - 1); got = try_at(pieces[pc], sv, pc)
    if got: items.append(got); need -= 1; print("P5B random piece", pc, flush=True)
pool = G["decoy_pool"](Pg, 5)["DP"]; picked = 0
for i in rng.permutation(len(pool)):
    if picked == 12: break
    k, r, c, g, dmin, f = pool[i]
    if any(np.hypot(r - it["rowcol"][0], c - it["rowcol"][1]) < G["SEP"] for it in items): continue
    img, segs, x = G["render"](Pg, r, c, g)
    if not G["visible_ok"](segs): REJ["control"] += 1; continue
    items.append({"group": "P5C", "page": 5, "piece": None, "rowcol": [r, c], "dir_rowcol": np.round(g, 4).tolist(), "xyz": x,
                  "min_dist_to_boundary_vox": round(4 * dmin, 1), "p3_any_share": round(f, 3), "img": img, "segs": segs}); picked += 1
print("P5B", sum(it["group"] == "P5B" for it in items), "P5C", picked, REJ, flush=True)
lo, hi = G["WIN"]; U, V = G["U"], G["V"]; ids = set(); os.makedirs(out, exist_ok=True); os.makedirs(sealed, exist_ok=True)
from PIL import ImageDraw
for it in items:
    while True:
        i = secrets.token_hex(4)
        if i not in ids: ids.add(i); it["id"] = i; break
    gimg = np.clip((it["img"] - lo) / (hi - lo), 0, 1) * 255
    im = Image.fromarray(gimg.astype(np.uint8)).convert("RGB").resize((gimg.shape[1] * 2, gimg.shape[0] * 2), Image.NEAREST)
    dr = ImageDraw.Draw(im); segs = G["clip_mid"](it["segs"])
    for a, b in segs: dr.line([tuple(2 * a), tuple(2 * b)], fill=(255, 220, 0), width=1)
    fn = os.path.join(out, f"{it['id']}.png"); im.save(fn)
    ya = np.asarray(im).astype(int); ymid = ((ya[..., 0] > 200) & (ya[..., 1] > 180) & (ya[..., 2] < 80))[:, 2 * (U - 50) + 2: 2 * (U + 50) - 1].sum()
    assert ymid == 0, ("yellow inside the masked band", int(ymid))
    it["sha256"] = hashlib.sha256(open(fn, "rb").read()).hexdigest(); it["min_dist_to_deck123_vox"] = round(float(G["T1"].query(it["xyz"])[0]), 1); del it["img"], it["segs"]
order_ = [items[i]["id"] for i in secrets.SystemRandom().sample(range(len(items)), len(items))]; byid = {it["id"]: it for it in items}
json.dump({"deck": "F2 page-5 masked deck", "window_u16": list(G["WIN"]), "px_per_vox": 2, "frame_vox": [2 * U + 1, 2 * V + 1], "masked_half_width_vox": 50,
           "order": [{"id": i, "sha256": byid[i]["sha256"]} for i in order_]}, open(os.path.join(out, "deck.json"), "w"), indent=1)
json.dump({"deck": "F2 p5", "visibility_rejected": REJ, "items": [byid[i] for i in order_]}, open(os.path.join(sealed, "key.json"), "w"), indent=1)
print("n", len(items), "key sha256", hashlib.sha256(open(os.path.join(sealed, "key.json"), "rb").read()).hexdigest())
