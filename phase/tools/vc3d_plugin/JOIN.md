# Join mode from the plugin's own menu (SessA instruction)

**Tools → Sheet check (joins)** runs the checker's join mode: CONTRACT A4.2's region form. No adapter is involved.
The plugin builds `vc_sheet_check --region Z Y X NZ NY NX --patches … --rel … --volume … --out …` itself
(`buildJoinInvocation`, `src/SheetCheckCore.*`). Overlay loading, project entries and the cluster dock are shared with
segment mode. Single-patch (segment) mode is unchanged.

## Join spec
Join mode needs a region, its patch set and pipeline9's `rel.csv`, which VC3D does not hold. They come from a small
JSON file. The menu reads `$VC_SHEET_CHECK_JOIN` if it is set, otherwise it opens a file dialog.

```json
{"region": [z, y, x, nz, ny, nx], "patches": ["patches.zip"], "rel": "rel.csv",
 "volume": "ct.zarr", "wrap_index": "...", "patch_table": "...", "axis_file": "...", "risk_model": "...",
 "scan_shape": [z, y, x]}
```
- Required: `region`, `patches`, `rel`.
- `volume` defaults to the current volume.
- Relative paths resolve against the spec's directory.
- `join/fixture_A.json` is fixture region A with its committed inputs. On a release, fetch the fixture first, as for
  `vc-sheet-check fixture`.

## Tests
- `run_join_test.sh <vc_sheet_check>`: headless; Qt offscreen, no VC3D.
  - It builds the Tools menu as villa's hook does, then triggers **Sheet check (joins)** from it on `join/fixture_A.json`.
  - The controller runs the **real** CLI. Measured on a fresh container (SessL, candidate-6): 94 s, peak RSS **5.3 GB**
    (the CLI's `max_rss_mb` 5306.7).
  - Checked: exit 0; contract-v1 `report.json`; the CLI's overlay attached, tagged and shown; report region equals
    the spec's; dock rows equal clusters; jump-to on row 0 goes to cluster 0's centroid.
  - Result (SessA, Qt 6.4.2): **ALL PASS**. 15 clusters, 130 pairs flagged.
- `run_unit_tests.sh` now also covers the join spec parser and argv (`testJoinSpec`): OK, 0 failures.
- The menu run **recomputes features from the CT**, so its flags are not the fixture golden. The golden comes from
  `vc-sheet-check fixture` with committed features. Against the golden, `test_fixture.py` fails the golden-equality
  checks (clusters, counts, flags, overlay_region, cleaned tifxyz) and passes the format checks. This is expected and
  is not a plugin result.

## Patches
`villa_sheet_check.patch` and `villa_hook.patch` were regenerated from villa `f4570bf` with these sources. The hook
gains one line: `_toolsMenu->addAction(sheetCheck->joinAction());`.
- The full patch applies to a clean `f4570bf` and reproduces `src/*` byte for byte.
- The hook patch applies on its own.
- **VC3D built here from this patch:** `build_vc3d.sh <fresh dir> --apt` ran in SessA's container (4 cores, Ubuntu,
  Qt 6.4.2), 292/292 targets in 11 min 34 s, exit 0.
  - Started with `QT_QPA_PLATFORM=offscreen`, it logs `vc.sheet_check: action registered` and stays up (stopped at
    40 s); the binary carries "Sheet check (joins)".
  - The in-app menu click was not run here.
  - This is not SessL's cold run on a fresh VM, which SessA instruction requires.
