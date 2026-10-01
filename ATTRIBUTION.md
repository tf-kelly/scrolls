# Attribution and licences

This tree is a scripted extract of tool code from a private research repository (see SOURCE_COMMIT.txt and
MANIFEST.txt). It contains code, the two trained switch models the tools default to, the small experiment tables
the tests read, and the integration fixture's own files and golden outputs. It contains no scan data, no patches, no
meshes, no figures and no whole-scroll results.

## Data the tools are written for (dataset sources)
- CT volumes and segments: Vesuvius Challenge open data, served from `https://dl.ash2txt.org/` and
  `https://vesuvius-challenge-open-data.s3.amazonaws.com/`, under the Vesuvius Challenge data terms. The tools do not
  redistribute any of it; scripts fetch it from those sources.
- PHerc1667 (Scroll 4) is part of the EduceLab-Scrolls dataset; cite EduceLab-Scrolls and Parsons et al. (2023),
  arXiv:2304.02084.
- The June 2026 PHerc1667 (Scroll 4) reference surface (arXiv:2606.29085) is licensed
  CC BY-NC 4.0 (`LICENSE.txt` at the bucket root).

## Fixture data (`phase/data_small/fixture/`)
- Not shipped, fetched by `fetch_fixture.py` from the public sources with a per-file sha256 check against
  `provenance.json`: the 1,712 patch members (W. Stevens' upload, below) and the region-A CT chunks (Vesuvius
  Challenge open data, under its data terms).
- Shipped: `reference_subset.npz`, an adaptation of the June 2026 PHerc1667 (Scroll 4) reference surface (x4
  upsampled vertices near fixture patches, with a computed reference turn). The source surface is licensed CC BY-NC
  4.0; this adaptation is shared under the same licence, for non-commercial use, with attribution to its authors.

## W. Stevens' published patches and reports
- Scroll 4 patch sets are W. Stevens' community upload, `https://dl.ash2txt.org/community-uploads/will/`, and his
  method is described in `https://github.com/WillStevens/scrollreading` (report12). No licence file is in the upload.

## The team's data and fitter (villa)
- The Spiral fitter, VC3D and data catalogue are from `https://github.com/ScrollPrize/villa` and its authors. The
  `*.patch` files and `phase/arc/` scripts run or modify that code; see the upstream repository for its licence.
- Vendored code under `*/_vendor/` keeps its origin record in `PROVENANCE.json`.

## ARC acknowledgement
- The authors would like to acknowledge the use of the University of Oxford Advanced Research Computing (ARC)
  facility in carrying out this work (http://dx.doi.org/10.5281/zenodo.22558).
