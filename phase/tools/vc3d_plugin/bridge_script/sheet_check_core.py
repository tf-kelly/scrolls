"""Non-GUI rules shared with the C++ plugin (src/SheetCheckCore.cpp): same schema checks, overlay choice,
placement guard and axis swap. Standard library only."""
import json, math, os

CONTRACT = "v1"
KINDS = ("suspect_join", "wrong_turn")


class ReportError(ValueError):
    pass


def build_argv(program, segment, volume, out_dir):
    return [program, "--segment", segment, "--volume", volume, "--out", out_dir]


def _vec3(v):
    if not isinstance(v, list) or len(v) != 3:
        return None
    if not all(isinstance(a, (int, float)) and not isinstance(a, bool) and math.isfinite(a) for a in v):
        return None
    return [float(a) for a in v]


def parse_report(text):
    try:
        root = json.loads(text)
    except ValueError as e:
        raise ReportError(f"report.json is not valid JSON: {e}")
    if not isinstance(root, dict):
        raise ReportError("report.json top level is not an object")
    if root.get("contract") != CONTRACT:
        raise ReportError(f'report.json contract is "{root.get("contract")}", expected "{CONTRACT}"')
    status = root.get("status", "")
    if status and status != "ok":  # Amendment 4 A4.2
        raise ReportError(f'vc_sheet_check reported status "{status}": {root.get("error", "")}')
    region = root.get("region") or {}
    origin, shape = _vec3(region.get("origin_zyx")), _vec3(region.get("shape_zyx"))
    if origin is None or shape is None:
        raise ReportError("report.json region needs origin_zyx and shape_zyx")
    ov_origin, ov_shape = origin, shape  # pre-A10 report: the overlay covers region
    if "overlay_region" in root:  # A10.2: where the overlay has chunks
        ovr = root.get("overlay_region") or {}
        ov_origin, ov_shape = _vec3(ovr.get("origin_zyx")), _vec3(ovr.get("shape_zyx"))
        if ov_origin is None or ov_shape is None:
            raise ReportError("report.json overlay_region needs origin_zyx and shape_zyx")
    if not isinstance(root.get("clusters"), list):
        raise ReportError('report.json has no "clusters" array')
    clusters = []
    for i, o in enumerate(root["clusters"]):
        o = o if isinstance(o, dict) else {}
        cid = o.get("id")
        if not isinstance(cid, int) or isinstance(cid, bool):
            raise ReportError(f"cluster {i} has no integer id")
        if o.get("kind") not in KINDS:
            raise ReportError(f'cluster {cid} has unknown kind "{o.get("kind")}"')
        c = _vec3(o.get("centroid_zyx"))
        if c is None:
            raise ReportError(f"cluster {cid} has no valid centroid_zyx")
        bb = o.get("bbox_zyx")
        if not (isinstance(bb, list) and len(bb) == 2 and _vec3(bb[0]) and _vec3(bb[1])):
            raise ReportError(f"cluster {cid} has no valid bbox_zyx")
        mr = o.get("max_risk")
        clusters.append({"id": cid, "kind": o["kind"], "centroid_zyx": c,
                         "n_pairs": int(o.get("n_pairs", 0) or 0), "n_patches": int(o.get("n_patches", 0) or 0),
                         "area_cm2": float(o.get("area_cm2", 0.0) or 0.0),
                         "max_risk": float(mr) if isinstance(mr, (int, float)) and not isinstance(mr, bool) else None})
    return {"contract": root["contract"], "status": status, "region_origin_zyx": origin, "region_shape_zyx": shape,
            "overlay_origin_zyx": ov_origin, "overlay_shape_zyx": ov_shape,
            "pairs_flagged": int((root.get("counts") or {}).get("pairs_flagged", 0) or 0), "clusters": clusters}


def choose_overlay(out_dir):
    for name in ("overlay_vc3d.zarr", "overlay.zarr"):
        p = os.path.join(out_dir, name)
        if os.path.isdir(p):
            return os.path.abspath(p)
    return None


def overlay_placement_problem(overlay_dir):
    """Non-empty if the overlay's OME level transforms carry a non-zero translation. VC3D's local reader
    ignores translations and draws the array from scan index 0 (placement probe, variant 'region')."""
    try:
        attrs = json.load(open(os.path.join(overlay_dir, ".zattrs")))
    except (OSError, ValueError):
        try:
            attrs = json.load(open(os.path.join(overlay_dir, "zarr.json"))).get("attributes", {})
        except (OSError, ValueError):
            return ""
    for ds in ((attrs.get("multiscales") or [{}])[0].get("datasets") or []):
        for t in ds.get("coordinateTransformations") or []:
            if t.get("type") == "translation" and any(v != 0 for v in t.get("translation", [])):
                return (f"{overlay_dir} has a non-zero OME translation, which VC3D cannot place. "
                        "The CLI should write overlay_vc3d.zarr (zero translation, scan frame).")
    return ""


def to_vc3d_xyz(zyx):
    return [zyx[2], zyx[1], zyx[0]]


def describe(c):
    z, y, x = c["centroid_zyx"]
    s = (f'#{c["id"]} {c["kind"]}  z={z:.0f} y={y:.0f} x={x:.0f}  pairs={c["n_pairs"]} '
         f'patches={c["n_patches"]}  {c["area_cm2"]:.3f} cm2')
    if c["max_risk"] is not None:
        s += f'  switch={c["max_risk"]:.2f}'  # Amendment 3: switch score, not an error estimate
    return s


def inside_region(rep, c):
    o, s = rep["overlay_origin_zyx"], rep["overlay_shape_zyx"]  # A10.2 overlay_region, else region
    return all(o[i] <= c["centroid_zyx"][i] < o[i] + s[i] for i in range(3))


def describe_in(rep, c):
    return describe(c) + ("" if inside_region(rep, c) else "  [outside overlay region]")
