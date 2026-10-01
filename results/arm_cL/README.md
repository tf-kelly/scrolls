# Fit c (arm_cL): whole-scroll flatten and overview render, Scroll 4

Run records only. The flattened surface and the rendered image are **not in this repository**. The image is a
render of the CT, and the data server's terms do not allow redistributing it without written approval. The surface
is about 67 MB; it will be offered to the team after submission. Their hashes and storage paths are below.

| File here | What it records |
|---|---|
| `flatten.json` | Export and flatten of fit c's surface: exported windings [0, 44], taken from PLACE's snapped range [0, 43] ± 1; capacity 144; flat surface 647 × 11,337 cells, 6,618,365 valid; wall time 1,141.9 s; torch peak 2.87 GB on one NVIDIA L4 |
| `picture.json` | Overview render: 3,231 × 56,681 px at 31.64 µm/px (CT level 2); 165,002,000 surface pixels, 1,848,352 of them unavailable; surface area 1,651.8 cm² (3-D, fitted surface); 3,329 CT chunks read, 0 missing |

**Inputs:**
- checkpoint `final.ckpt`, sha256 `75692010bf247e84490d6a17136df7ca1a4c5467255b7744c1a7d1ca742788f3` (iteration 30,000);
- tools: `vc_scale` bundle r6 (sha256 `a4f12e50…`, SHA256SUMS checked on the machine), with `render.py` unmodified;
- villa image sha256 `387138e4…`;
- CT: Scroll 4 (PHerc 1667) scan `20231117161658`, public zarr.

The overview was rendered without PLACE's quads, so it has no support map and no crops.

**Not shipped (private store, `<private-bucket>/gpu_cL/run1/`):**

| Object | Bytes | sha256 |
|---|---:|---|
| `flatten/arm_cL/flat.tifxyz/x.tif` | 23,490,750 | `2c51917de73cbcac78939abdddcfe8a5e2dae6ea6a6976e3a553fe0ee4360432` |
| `flatten/arm_cL/flat.tifxyz/y.tif` | 23,451,287 | `a9cea7a6468963befe3f4dd15626ac03f91d3789697d8a84ccf1cb1ad2f72825` |
| `flatten/arm_cL/flat.tifxyz/z.tif` | 20,627,039 | `223a55c074ab5b399e11b85f1e31da5aaf3d17a2ecf860d857b4094848ff6217` |
| `flatten/arm_cL/flat.tifxyz/meta.json` | 10,322 | `edd205d99d5f1f475688801431587e3fb98c280cbed3897e86b7d5f90ea69a58` |
| `render/arm_cL/overview_small.jpg` | 2,600,771 | `03b700ddc07e50e01e9e40bd30498abaf32aad2948e6695c085d0306971ed71a` |

The `.jpg` is a folded, downsampled copy of the picture (1,445 × 4,000 px). The paths inside the two JSON files are
paths on the machine that ran the job.

A surface area is not verified papyrus, and a picture is not evidence that the fit is correct.
