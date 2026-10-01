
This repository assigns winding numbers to overlapping surface patches and lists the joins where those numbers disagree with the measured relationships. I developed it using Will Stevens' patch release for P.Herc.1667 (Scroll 4). It also includes a CT-based sheet checker and tools for passing the winding numbers to the Vesuvius Challenge team's spiral fitter.

In general, an important problem with a patch-based approach to unwrapping is that patch can move onto a neighbouring sheet while still overlapping other patches. Local joins may look plausible but disagree when followed around the scroll. The index solves for integer winding numbers across each connected component in a way that minimises the total absolute disagreement with the measurements. Disagreements can then be adjudicated by eye.

The optimisation is exact for the supplied constraints. The measurements can still be wrong, and a patch can cross sheets without creating a contradiction. A winding number is therefore an estimate of the patch's place in the scroll, not a certificate that the patch follows one sheet.

On Stevens' release, the index assigns numbers to 56,934 of 56,968 patches and leaves 15,154 joins with at least one unsatisfied constraint (the other 34 patches don't have usable joins). The outputs keep Stevens's patch IDs, so they can be compared directly with his retained and removed sets.

Whole-scroll fitting is still work in progress. The outermost windings disagree with the published segmentation, and the current results do not establish a complete, continuous surface suitable for reading. More details are given in the main write-up.

For P.Herc.1667 the repo includes the saved whole-scroll assignment and unsatisfied constraints -- run as

```bash
git clone https://github.com/tf-kelly/scrolls.git
cd scrolls
mkdir -p OUT
python3 community/build_s4_index.py OUT
```

which checks the input hashes and writes

- `OUT/winding.csv`: 56,934 rows, with `patch_id`, `component`, `winding` and `theta_rad`.
- `OUT/contradictions.json`: 15,154 joins containing 23,857 violated constraints, with measured and solved differences.

For the fixture, fitting requires an NVIDIA GPU and a separate installation of `villa`.

From the repo root:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r phase/tools/requirements.txt \
  -e phase/tools/vc_sheet_check -e phase/tools/vc_unwrap

python phase/data_small/fixture/fetch_fixture.py
python phase/tools/test_metrics.py
python phase/tools/test_fixture.py
vc-unwrap run --fixture --until export --out U
```

The downloader retrieves the fixture's patch files and CT chunks from the public data server and checks their SHA-256 hashes. It fetches 428 patches; the fixture region's solve uses 229. The recorded fixture check used about 5.3 GB of RAM. Allow several minutes for the download and CPU stages.

The main outputs are:

| Path | Contents |
| --- | --- |
| `U/check/wrap_index.csv` | Winding assignment and component for each indexed patch |
| `U/check/unsatisfied.csv` | Constraints left unsatisfied by the assignment |
| `U/check/switch_risk.csv` | The join checker's switch scores |
| `U/check/overlay.zarr` | Flags for inspection in VC3D |
| `U/dataset/same_windings.json` | Same-winding point collections |
| `U/dataset/relative_windings.json` | Relative-winding point collections |
| `U/UNWRAP_MANIFEST.json` | Run settings, stage results and timings |

Without `--villa`, the export stops before villa's loader filter and patch-name check. See [the fitter instructions](phase/tools/vc_unwrap/README.md) for those steps and for fitting and exporting per-winding tifxyz surfaces. Villa is pinned to commit `f4570bf`.

`test_metrics.py` skips a ledger-dependent check whose inputs are not in this release. 


For other data:

`vc-sheet-check` accepts tifxyz patches and OME-Zarr CT data. A new region needs its scan dimensions, voxel size, axis and spacing, together with the patch relationship inputs. The exact arguments are listed in [the tool instructions](phase/tools/vc_unwrap/README.md). Start with

```bash
vc-sheet-check region --help
vc-sheet-check segment --help
vc-unwrap run --help
```

Region mode checks joins and solves the winding assignment. Segment mode checks within a mesh. The checker estimates sheet changes. NB change is not necessarily an error, since patches on different windings can form a valid relative-winding constraint. Performance falls on held-out regions, especially where sheets touch.

There is a draft [VC3D integration](phase/tools/vc3d_plugin/JOIN.md). Join mode has been exercised on the fixture through a headless menu test. 


When fitting, check the initial spacing and winding capacity explicitly. With dense-spacing inputs disabled (published versions for scroll 4 couldn't be found, and computing them was beyond the scope of this), the original Scroll 4 runs at 16 voxels per winding produced 95 fitted windings. Runs starting at 32 voxels, with the winding cap also changed, produced 43–45. The fitter's satisfied-patch score alone did not identify the excessive turn count.


[docs/CLAIMS.md](docs/CLAIMS.md) records the results, their sources and limitations. [REGISTRATIONS.md](REGISTRATIONS.md) records the planned tests and outcomes. Some supporting inputs remain outside this release, as described above.

The Scroll 4 patches were grown by [Will Stevens](https://github.com/WillStevens/scrollreading/tree/main/pipeline9) and released with report 12: [retained patches](https://dl.ash2txt.org/community-uploads/will/s4_good_patches.zip) and [removed patches](https://dl.ash2txt.org/community-uploads/will/s4_bad_patches.zip). This work uses both sets. The CT is P.Herc.1667, volume `20231117161658`, at 7.91 micrometres per voxel. The spiral fitter is the Vesuvius Challenge team's [villa](https://github.com/ScrollPrize/villa/tree/f4570bf/spiral-fitting).

The code is MIT-licensed. Data and derived fixtures have separate terms; see [LICENSES.md](LICENSES.md) and [ATTRIBUTION.md](ATTRIBUTION.md). The published reference reconstruction is used for comparison, not treated as exact ground truth.

I developed the code and analyses with AI coding agents under my supervision. The human blind readings reported here were mine.
