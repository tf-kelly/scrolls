"""SessE-8 (1) name check: load the exported patches and each arm's role files with villa's OWN code (tifxyz.load_tifxyz,
spiral_helpers erosion, point_collection.load_point_collection / link_points_to_patches at villa a92521b), using the
fitter's link call (fit_spiral: tolerance = surface_index_tolerance = pcl_link_distance_tolerance 2.5,
distance_scale 1.0, general_hit_policy 'largest_area', default link options) and the fit's z-range.
FAILS (exit 1) if any point of a between_patches__A__B collection attaches to a patch other than its own
(point 1 -> A, point 2 -> B). Unattached points are counted, not failures (villa drops them silently).
Usage: python name_check.py VILLA_SRC DATASET_ROOT OUT_JSON [Z_BEGIN Z_END]"""
import json, os, sys, time
from pathlib import Path

import numpy as np

ALLOW_SAME_TIES = "--allow-same-winding-ties" in sys.argv          # amendment 12 gate semantics
ARGS = [a for a in sys.argv if a != "--allow-same-winding-ties"]
VILLA, ROOT, OUT = Path(ARGS[1]), Path(ARGS[2]), Path(ARGS[3])
ZB, ZE = (int(ARGS[4]), int(ARGS[5])) if len(ARGS) > 5 else (4096, 4864)
sys.path.insert(0, str(VILLA))
import scipy.ndimage  # noqa: E402
from tifxyz import load_tifxyz  # noqa: E402
import point_collection as pc  # noqa: E402

ERODE_DEFAULT, TOL = 1, 2.5          # config.patch_erode_patches, config.pcl_link_distance_tolerance (a92521b)


def erode_patch_valid_region(patch, num_cells):
    """Verbatim from villa spiral_helpers.erode_patch_valid_region @ a92521b (copied: that module's other imports
    pull in the whole fitter)."""
    SRC = (VILLA / "spiral_helpers.py").read_text()
    i = SRC.index("def erode_patch_valid_region"); j = SRC.index("\ndef ", i + 10)
    ns = {"scipy": scipy, "np": np, "torch": __import__("torch")}
    exec(SRC[i:j], ns)
    return ns["erode_patch_valid_region"](patch, num_cells)


def load_patches():
    """spiral_helpers.load_patch_payload_chunk.load_one, minus the payload round-trip."""
    patches, drops = {}, {}
    for entry in sorted(os.listdir(ROOT / "verified_patches")):
        patch = load_tifxyz(str(ROOT / "verified_patches" / entry), z_range=(ZB, ZE))
        if patch is None:
            drops[entry] = "z ROI prefilter"; continue
        cells = patch.erosion_cells(ERODE_DEFAULT)
        if cells > 0 and not erode_patch_valid_region(patch, cells):
            drops[entry] = "erosion"; continue
        zs = patch.valid_zyxs[:, 0] if hasattr(patch, "valid_zyxs") else None
        if zs is not None and not bool(((zs >= ZB) & (zs < ZE)).any()):
            drops[entry] = "z ROI after erosion"; continue
        patches[entry] = patch
    return patches, drops


def main():
    t0 = time.time()
    patches, drops = load_patches()
    res = dict(villa="a92521b spiral-fitting (tifxyz, point_collection, spiral_helpers.erode_patch_valid_region)",
               dataset=str(ROOT), z_range=[ZB, ZE], tolerance_vox=TOL, erode_cells_default=ERODE_DEFAULT,
               patches_loaded=len(patches), patches_dropped={r: sum(1 for v in drops.values() if v == r) for r in set(drops.values())}, files={})
    fail = 0
    for fn in ("same_windings.json", "relative_windings.json"):
        f = ROOT / fn
        if not f.exists():
            continue
        cols = pc.load_point_collection(str(f))
        if os.environ.get("SC_LIMIT"):                   # smoke test only: the first N collections
            cols = dict(list(cols.items())[:int(os.environ["SC_LIMIT"])])
            res["limited_to"] = int(os.environ["SC_LIMIT"])
        if os.environ.get("SC_SAMPLE"):                  # seeded random sample of N collections per file (seed 0)
            keys = sorted(cols); pick = np.random.default_rng(0).choice(len(keys), min(int(os.environ["SC_SAMPLE"]), len(keys)), replace=False)
            cols = {keys[i]: cols[keys[i]] for i in sorted(pick)}
            res["random_sample_per_file"] = int(os.environ["SC_SAMPLE"])
        pc.link_points_to_patches(patches, cols, tolerance=TOL, surface_index_tolerance=TOL, distance_scale=1.0,
                                  general_hit_policy="largest_area", options=pc.DEFAULT_LINK_OPTIONS)
        n = own = wrong = unatt = both_att = unresolved_names = allowed_ties = 0; examples = []
        for c in cols.values():
            a, b = c["name"][len("between_patches__"):].split("__")
            if a not in patches or b not in patches:
                unresolved_names += 1                     # villa would fall back to the general nearest-patch search
            pts = [c["points"][k] for k in sorted(c["points"])]
            got = []
            for want, pt in zip((a, b), pts):
                n += 1
                on = pt.get("on_patch", {}).get("id") if "on_patch" in pt else None
                if on is None:
                    unatt += 1
                elif str(on) == want:
                    own += 1
                elif ALLOW_SAME_TIES and fn == "same_windings.json" and str(on) in (a, b):
                    allowed_ties += 1                     # attached to its own collection's other named patch: trivially satisfied
                else:
                    wrong += 1
                    if len(examples) < 20:
                        examples.append(dict(collection=c["name"], expected=want, attached=str(on), p=pt["p"]))
                got.append(on)
            both_att += all(g is not None for g in got)
        res["files"][fn] = dict(collections=len(cols), points=n, attached_to_own=own, attached_to_other=wrong, allowed_same_winding_ties=allowed_ties, unattached=unatt,
                                collections_fully_attached=both_att, collections_with_unloaded_names=unresolved_names,
                                wrong_examples=examples)
        fail += wrong
    res["allow_same_winding_ties"] = ALLOW_SAME_TIES
    res["PASS"] = fail == 0
    res["seconds"] = round(time.time() - t0, 1)
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "files"}, indent=1))
    for fn, v in res["files"].items():
        print(fn, {k: x for k, x in v.items() if k != "wrong_examples"})
    sys.exit(0 if res["PASS"] else 1)


if __name__ == "__main__":
    main()
