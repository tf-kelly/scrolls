# Spiral constraints: record schema (contract v1 §4.5)

> **Superseded by contract Amendment 2** (`phase/tools/CONTRACT.md`), which replaces §4.5's
> delegation and fixes the format in the contract itself: role files in `<out>/spiral/`, envelope
> `format = "vc_pointcollections_json v1"`. `phase/sc/convert.py` `write_points` implements Amendment 2. This file is
> kept only as the record of the earlier proposal.

Producer: `phase/sc/convert.py`. This file defines the `constraints` records inside
the frozen §4.5 envelope. It does not redefine §1–§3.

## Envelope values

`"format": "sc.villa-relative-pairs/1"`, `"frame": "scan voxels zyx, 7.91 um"`, `"wrap_index_source": "§2"`.
Extra keys: `villa_files` (sha256 of the villa-native files written alongside), `weighting` (`uniform` by default).

## Record (one per kept patch pair)

| field | type | meaning |
|---|---|---|
| `patch_a`, `patch_b` | int | the pair, as in `phase/x6/x6b_pairs.csv` |
| `delta_winding` | int | physical winding difference b − a: `k_b − k_a − c`, where `c = refmesh.cross(θ_a, θ_b)` ∈ {−1, 0, +1} and s = +1 (§2). +1 = b is one sheet outward of a. |
| `weight` | float | 1.0 under `uniform` (default). Other values appear only if a risk is adopted (see below). |
| `copies` | int | how many identical villa collections carry this record (1 under `uniform`) |
| `point_a_zyx`, `point_b_zyx` | [z, y, x] float voxels | anchor on each patch: X6's evaluated point pair with the smallest separation |

**Seam removal.** §2's index is cut at θ0 = +x: going the short way from θ_a to θ_b across θ0
counter-clockwise (θ rising through 2π → 0), c = +1, and the index of the same physical sheet jumps
by +1 (`t = k + θ/2π` continuous). `delta_winding` subtracts c, so it is seam-free. villa's relative
loss applies its own θ = 0 crossing correction along each collection's chain
(`losses._pcl_chain_seam_adjustments`), so it needs exactly this seam-free number.

**Omitted:** pairs touching a patch without a wrap index, or with the converter's abstention flag.

## villa-native file written next to the envelope

`relative_windings.json`, VC3D `vc_pointcollections_json_version "1"`: per record, `copies` 2-point
collections named `between_patches__<a>__<b>`, points `{"p": [x, y, z], "wind_a": 0}` and
`{"p": [x, y, z], "wind_a": delta_winding}`. villa reads `p` as x,y,z and reverses it itself.
villa has no hard constraints and no per-constraint weight (see `phase/sc/CONTRACT_REQUEST.md`).

## Weighting

`uniform` is the default and the only mode to deploy until a risk beats chance at identifying *wrong
constraints*. Two risks have been tried: a per-patch LP-violation rate (AUC 0.48) and contract
risk v1 (AUC 0.506 on the 453 wrong edges against matched correct ones). Contract risk v1 is
trained on labels from the same solve that produced the index, so it largely restates the index.
`replicate` (round(4·w) copies) and `tiers` (service only) are retained for a future risk.
