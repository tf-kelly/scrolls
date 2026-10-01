#!/usr/bin/env bash
# Adapter for the in-app test only: runs SessA's REAL checker in REGION mode on fixture region A, using SessA's own
# command line (`vc-sheet-check fixture --out DIR`, phase/tools/vc_sheet_check/README.md at <branch> da5da56).
# The plugin's --segment/--volume are ignored: region mode takes a region and its patch set, not one segment.
# Env: SHEET_CHECK_TREE = a checkout of <branch> at da5da56; SHEET_CHECK_BIN = its installed vc-sheet-check.
set -euo pipefail
while [ $# -gt 0 ]; do case $1 in --out) OUT=$2; shift 2;; --segment|--volume|--halo-um|--threshold) shift 2;; *) shift;; esac; done
cd "${SHEET_CHECK_TREE:?}"
exec "${SHEET_CHECK_BIN:?}" fixture --out "$OUT"
