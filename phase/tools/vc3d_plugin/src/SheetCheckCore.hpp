#pragma once

// Sheet check: non-GUI half of the VC3D wiring for the vc_sheet_check CLI.
// All analysis lives in the CLI. This file only builds its command line,
// reads its report.json (integration contract v1, section 4.1), picks the
// overlay to load, and converts coordinates into VC3D's convention.
// Depends on Qt Core only, so it is unit-tested without the rest of VC3D.

#include <QString>
#include <QStringList>

#include <array>
#include <optional>
#include <vector>

namespace sheetcheck {

using Zyx = std::array<double, 3>;

// One entry of report.json "clusters". Coordinates are scan voxels in
// (z, y, x) as the contract writes them; use toVc3dXyz() before handing
// them to VC3D, whose volume points are (x, y, z).
struct Cluster {
    qint64 id{0};
    QString kind;  // "suspect_join" | "wrong_turn"
    Zyx centroidZyx{};
    Zyx bboxLoZyx{};
    Zyx bboxHiZyx{};
    qint64 nPairs{0};
    qint64 nPatches{0};
    double areaCm2{0.0};
    // report.json "max_risk". Amendment 3: this is the SWITCH SCORE (where the
    // wrap index changes), not an error or confidence estimate.
    std::optional<double> maxRisk;  // null for wrong_turn clusters
};

struct Report {
    QString contract;  // "v1"
    QString status;    // Amendment 4 A4.2: "ok" (absent in pre-A4 reports)
    QString git;
    Zyx regionOriginZyx{};
    Zyx regionShapeZyx{};
    // A10.2: where the overlay has chunks (report.json "overlay_region"); equals region when absent (pre-A10).
    Zyx overlayOriginZyx{};
    Zyx overlayShapeZyx{};
    qint64 pairsFlagged{0};
    std::vector<Cluster> clusters;
};

struct ParseResult {
    std::optional<Report> report;
    QString error;  // set iff !report
};

struct Invocation {
    QString program;
    QStringList arguments;
    QString outDir;
    QString reportPath;
};

// argv for one run: contract A4.2's form, plus "--axis-file <axisFile>"
// when one is given (segment mode requires it, contract A5.3).
Invocation buildInvocation(const QString& cliProgram,
                           const QString& segmentPath,
                           const QString& volumePath,
                           const QString& outDir,
                           const QString& axisFile = {});

// Join mode: contract A4.2's region form. The checker scores the joins
// between overlapping patches in one chunk-aligned region, so it needs the
// region, its patch set and pipeline9's rel.csv, which VC3D does not hold.
// They come from a join spec, a small JSON file:
//   {"region": [z, y, x, nz, ny, nx], "patches": ["patches.zip"], "rel": "rel.csv",
//    "volume": "ct.zarr", "wrap_index": "...", "patch_table": "...",
//    "axis_file": "...", "risk_model": "...", "scan_shape": [z, y, x]}
// "region", "patches" and "rel" are required; "volume" defaults to the
// current volume. Relative paths resolve against the spec's directory.
struct JoinSpec {
    std::array<qint64, 6> region{};  // z, y, x, nz, ny, nx (level-0 voxels)
    QStringList patches;
    QString rel;
    QString volume;
    QString wrapIndex;
    QString patchTable;
    QString axisFile;
    QString riskModel;
    std::optional<std::array<qint64, 3>> scanShape;
};

struct JoinSpecResult {
    std::optional<JoinSpec> spec;
    QString error;  // set iff !spec
};

JoinSpecResult parseJoinSpec(const QByteArray& json, const QString& baseDir);
JoinSpecResult parseJoinSpecFile(const QString& path);

// argv for one join run: "--region Z Y X NZ NY NX --patches ... --rel R
// --volume V --out O" plus the spec's optional arguments. volumePath is used
// when the spec names no volume.
Invocation buildJoinInvocation(const QString& cliProgram,
                               const JoinSpec& spec,
                               const QString& volumePath,
                               const QString& outDir);

// Project-entry key for a join run, used where segment mode uses the
// segment id: "region:Z_Y_X_NZ_NY_NX".
QString joinEntryKey(const JoinSpec& spec);

ParseResult parseReport(const QByteArray& json);
ParseResult parseReportFile(const QString& reportPath);

// The overlay directory to attach: <outDir>/overlay_vc3d.zarr when the CLI
// wrote one (zero-translation view VC3D can open), else <outDir>/overlay.zarr.
// Empty if neither exists.
QString chooseOverlay(const QString& outDir);

// Non-empty if VC3D cannot place this overlay correctly: an OME level
// transform (Zarr v2 .zattrs or v3 zarr.json attributes) has a non-zero
// translation. VC3D's local reader ignores translations (villa f4570bf,
// openLocalZarrPyramid) and draws the array from scan index 0, silently;
// the plugin refuses such an overlay instead.
QString overlayPlacementProblem(const QString& overlayDir);

// Project-file bookkeeping. The plugin tags its overlay entries with
// kEntryTag and segmentTag(segmentId), keeping one entry per segment.
struct ProjectEntry {
    QString location;
    QStringList tags;
};
inline constexpr const char* kEntryTag = "sheet_check";
QString segmentTag(const QString& segmentId);  // "sheet_check_segment:<id>"
QStringList overlayEntryTags(const QString& segmentId);

// Locations to remove from the project before attaching newLocation for
// segmentId: sheet_check entries of the same segment (replace, not append)
// and sheet_check entries of any segment whose directory no longer exists.
// Entries without the sheet_check tag are never touched.
QStringList staleOverlayEntries(const std::vector<ProjectEntry>& entries,
                                const QString& segmentId,
                                const QString& newLocation);

// (z, y, x) -> (x, y, z). Kept as a named function so the swap is tested.
std::array<float, 3> toVc3dXyz(const Zyx& zyx);

// True if the centroid lies inside the overlay region: A10.2's "overlay_region", or
// "region" for a pre-A10 report. Chunks are written only there, so outside it nothing is drawn.
bool insideRegion(const Report& r, const Cluster& c);

QString describe(const Cluster& c);  // one line for the dock list
QString describe(const Report& r, const Cluster& c);  // + "[outside overlay region]"

}  // namespace sheetcheck
