// Unit tests for the non-GUI half of Tools -> Sheet check (contract v1).
// Qt Core only. Usage: test_sheet_check_core [golden_out_dir]
// golden_out_dir is a directory written by phase/tools/example_outputs.py
// (region A of the fixture, v1.1). Its report.json is checked against the
// values the fixture README commits to (region, overlay_region, counts, 30 + 21 clusters; fixture v1.4).

#include "SheetCheckCore.hpp"

#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QTemporaryDir>

#include <cstdio>

using namespace sheetcheck;

static int failures = 0;
#define CHECK(cond)                                                              \
    do {                                                                         \
        if (!(cond)) {                                                           \
            std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
            ++failures;                                                          \
        }                                                                        \
    } while (0)

// Schema-shaped report per CONTRACT.md 4.1. Hand-written: the golden report
// has no clusters, so cluster fields are only testable this way.
static const QByteArray kSchemaReport = R"({
  "contract": "v1", "git": "abc", "branch": "<branch>",
  "region": {"origin_zyx": [4224, 2560, 640], "shape_zyx": [384, 384, 384]},
  "inputs": {}, "counts": {"pairs_flagged": 3},
  "clusters": [
    {"id": 0, "kind": "suspect_join", "n_pairs": 2, "n_patches": 3, "area_cm2": 0.0125,
     "centroid_zyx": [4300.5, 2700.25, 800.0],
     "bbox_zyx": [[4290, 2690, 790], [4310, 2710, 810]],
     "theta_deg": 130.0, "wrap_index_range": [3, 4],
     "patches": [1, 2, 3], "pairs": [[1, 2], [2, 3]], "max_risk": 0.91},
    {"id": 1, "kind": "wrong_turn", "n_pairs": 0, "n_patches": 1, "area_cm2": 0.002,
     "centroid_zyx": [4500, 2900, 1000],
     "bbox_zyx": [[4490, 2890, 990], [4510, 2910, 1010]],
     "theta_deg": 131.0, "wrap_index_range": [5, 5],
     "patches": [9], "pairs": [], "max_risk": null}]})";

static void testInvocation()
{
    const auto inv = buildInvocation("/opt/bin/vc_sheet_check", "/s/seg 1", "/v/vol.zarr", "/tmp/out");
    CHECK(inv.program == "/opt/bin/vc_sheet_check");
    CHECK(inv.arguments == QStringList({"--segment", "/s/seg 1", "--volume", "/v/vol.zarr",
                                        "--out", "/tmp/out"}));
    CHECK(inv.outDir == "/tmp/out");
    CHECK(inv.reportPath == "/tmp/out/report.json");
    const auto withAxis = buildInvocation("vc", "/s", "/v", "/o", "/p/umbilicus.json");
    CHECK(withAxis.arguments == QStringList({"--segment", "/s", "--volume", "/v", "--out", "/o",
                                             "--axis-file", "/p/umbilicus.json"}));
}

static void testJoinSpec()
{
    // Relative paths resolve against the spec's directory; a URL volume passes through.
    const auto r = parseJoinSpec(R"({"region": [4224, 2560, 640, 384, 384, 384], "patches": ["p/patches.zip"],
        "rel": "rel.csv", "volume": "https://h/s.zarr", "wrap_index": "../k.csv", "scan_shape": [11174, 3340, 3440]})",
                                 "/data/spec");
    CHECK(r.spec.has_value());
    if (!r.spec)
        return;
    CHECK(r.spec->patches == QStringList({"/data/spec/p/patches.zip"}));
    CHECK(r.spec->rel == "/data/spec/rel.csv");
    CHECK(r.spec->volume == "https://h/s.zarr");
    CHECK(r.spec->wrapIndex == "/data/k.csv");
    CHECK(joinEntryKey(*r.spec) == "region:4224_2560_640_384_384_384");
    const auto inv = buildJoinInvocation("vc", *r.spec, "/ignored.zarr", "/o");
    CHECK(inv.arguments == QStringList({"--region", "4224", "2560", "640", "384", "384", "384",
                                        "--patches", "/data/spec/p/patches.zip", "--rel", "/data/spec/rel.csv",
                                        "--volume", "https://h/s.zarr", "--out", "/o",
                                        "--wrap-index", "/data/k.csv", "--scan-shape", "11174", "3340", "3440"}));
    CHECK(inv.reportPath == "/o/report.json");
    // No volume in the spec: the current volume is used. A single patches string is accepted.
    const auto m = parseJoinSpec(R"({"region": [0, 0, 0, 128, 128, 128], "patches": "a.zip", "rel": "/abs/rel.csv"})", "/d");
    CHECK(m.spec.has_value());
    if (m.spec) {
        CHECK(m.spec->patches == QStringList({"/d/a.zip"}) && m.spec->rel == "/abs/rel.csv");
        CHECK(buildJoinInvocation("vc", *m.spec, "/cur.zarr", "/o").arguments
              == QStringList({"--region", "0", "0", "0", "128", "128", "128", "--patches", "/d/a.zip",
                              "--rel", "/abs/rel.csv", "--volume", "/cur.zarr", "--out", "/o"}));
    }
    // Errors: missing or malformed required fields.
    CHECK(!parseJoinSpec("[]", "/d").spec);
    CHECK(!parseJoinSpec(R"({"region": [0, 0, 0, 1, 1], "patches": ["a"], "rel": "r"})", "/d").spec);
    CHECK(!parseJoinSpec(R"({"region": [0, 0, 0, 1, 1, 0], "patches": ["a"], "rel": "r"})", "/d").spec);
    CHECK(!parseJoinSpec(R"({"region": [0, 0, 0.5, 1, 1, 1], "patches": ["a"], "rel": "r"})", "/d").spec);
    CHECK(!parseJoinSpec(R"({"region": [0, 0, 0, 1, 1, 1], "rel": "r"})", "/d").spec);
    CHECK(!parseJoinSpec(R"({"region": [0, 0, 0, 1, 1, 1], "patches": ["a"]})", "/d").spec);
    CHECK(!parseJoinSpec(R"({"region": [0, 0, 0, 1, 1, 1], "patches": ["a"], "rel": "r", "scan_shape": [1, 2]})", "/d").spec);
}

static void testSwap()
{
    const auto xyz = toVc3dXyz({10.0, 20.0, 30.0});  // z, y, x
    CHECK(xyz[0] == 30.0f && xyz[1] == 20.0f && xyz[2] == 10.0f);
}

static void testParseSchema()
{
    const auto r = parseReport(kSchemaReport);
    CHECK(r.report.has_value());
    if (!r.report)
        return;
    CHECK(r.report->contract == "v1");
    CHECK(r.report->regionOriginZyx == (Zyx{4224, 2560, 640}));
    CHECK(r.report->regionShapeZyx == (Zyx{384, 384, 384}));
    CHECK(r.report->pairsFlagged == 3);
    CHECK(r.report->clusters.size() == 2);
    const auto& a = r.report->clusters[0];
    CHECK(a.id == 0 && a.kind == "suspect_join" && a.nPairs == 2 && a.nPatches == 3);
    CHECK(a.centroidZyx == (Zyx{4300.5, 2700.25, 800.0}));
    CHECK(a.bboxLoZyx == (Zyx{4290, 2690, 790}) && a.bboxHiZyx == (Zyx{4310, 2710, 810}));
    CHECK(a.maxRisk && *a.maxRisk == 0.91);
    const auto& b = r.report->clusters[1];
    CHECK(b.kind == "wrong_turn" && !b.maxRisk);
    // Jump target for cluster 0 in VC3D order.
    const auto xyz = toVc3dXyz(a.centroidZyx);
    CHECK(xyz[0] == 800.0f && xyz[1] == 2700.25f && xyz[2] == 4300.5f);
    CHECK(describe(a) == "#0 suspect_join  z=4301 y=2700 x=800  pairs=2 patches=3  0.013 cm2  switch=0.91");
    CHECK(!describe(b).contains("switch"));
    // Region [4224,4608) x [2560,2944) x [640,1024): a inside, b (x=1000) inside, then move b outside in z.
    CHECK(insideRegion(*r.report, a) && !describe(*r.report, a).contains("outside"));
    Cluster out = b;
    out.centroidZyx = {5035.0, 2936.0, 934.0};
    CHECK(!insideRegion(*r.report, out) && describe(*r.report, out).endsWith("[outside overlay region]"));
    out.centroidZyx = {4608.0, 2600.0, 700.0};  // upper bound is exclusive
    CHECK(!insideRegion(*r.report, out));
    CHECK(!describe(a).contains("risk"));  // Amendment 3: never label it risk
}

static QByteArray withReplaced(const char* from, const char* to)
{
    QByteArray j = kSchemaReport;
    CHECK(j.contains(from));
    return j.replace(from, to);
}

static void testOverlayRegion()
{
    // A10.2: "overlay_region" (where chunks exist) decides the tag, not the analysis "region".
    const char* reg = R"("region": {"origin_zyx": [4224, 2560, 640], "shape_zyx": [384, 384, 384]},)";
    const auto r = parseReport(withReplaced(reg, R"("region": {"origin_zyx": [4224, 2560, 640], "shape_zyx": [384, 384, 384]},
  "overlay_region": {"origin_zyx": [3712, 2176, 384], "shape_zyx": [1408, 896, 1152], "halo_um": 380.0, "rule": "A10.2"},)"));
    CHECK(r.report.has_value());
    if (!r.report)
        return;
    CHECK(r.report->regionOriginZyx == (Zyx{4224, 2560, 640}));  // region keeps its meaning
    CHECK(r.report->overlayOriginZyx == (Zyx{3712, 2176, 384}) && r.report->overlayShapeZyx == (Zyx{1408, 896, 1152}));
    Cluster c = r.report->clusters[1];
    c.centroidZyx = {5035.0, 2936.0, 934.0};  // outside region, inside overlay_region
    CHECK(insideRegion(*r.report, c) && !describe(*r.report, c).contains("outside"));
    c.centroidZyx = {5120.0, 2936.0, 934.0};  // 3712 + 1408: upper bound is exclusive
    CHECK(!insideRegion(*r.report, c) && describe(*r.report, c).endsWith("[outside overlay region]"));
    // Present but malformed: rejected, not silently replaced by region.
    CHECK(!parseReport(withReplaced(reg, R"("region": {"origin_zyx": [4224, 2560, 640], "shape_zyx": [384, 384, 384]},
  "overlay_region": {"origin_zyx": [3712, 2176]},)")).report);
}

static void testParseErrors()
{
    CHECK(!parseReport("not json").report);
    CHECK(!parseReport("[]").report);
    CHECK(!parseReport(withReplaced(R"("contract": "v1")", R"("contract": "v2")")).report);
    CHECK(parseReport(withReplaced(R"("contract": "v1")", R"("contract": "v2")")).error.contains("v2"));
    CHECK(!parseReport(withReplaced(R"("origin_zyx": [4224, 2560, 640])", R"("origin_zyx": [4224, 2560])")).report);
    CHECK(!parseReport(withReplaced(R"("clusters": [)", R"("clusterz": [)")).report);
    CHECK(!parseReport(withReplaced(R"("kind": "wrong_turn")", R"("kind": "other")")).report);
    CHECK(!parseReport(withReplaced(R"("centroid_zyx": [4500, 2900, 1000])", R"("centroid_xyz": [1000, 2900, 4500])")).report);
    CHECK(!parseReport(withReplaced(R"("bbox_zyx": [[4490, 2890, 990], [4510, 2910, 1010]])", R"("bbox_zyx": [[4490, 2890, 990]])")).report);
    CHECK(!parseReport(withReplaced(R"("id": 1,)", R"("id": "1",)")).report);
    CHECK(!parseReportFile("/nonexistent/report.json").report);
    // Amendment 4 A4.2 status field
    CHECK(parseReport(withReplaced(R"("git": "abc")", R"("git": "abc", "status": "ok")")).report.has_value());
    const auto st = parseReport(withReplaced(R"("git": "abc")", R"("git": "abc", "status": "error", "error": "bad segment")"));
    CHECK(!st.report && st.error.contains("bad segment"));
}

static void testChooseOverlay()
{
    QTemporaryDir t;
    CHECK(t.isValid());
    CHECK(chooseOverlay(t.path()).isEmpty());
    QDir(t.path()).mkdir("overlay.zarr");
    CHECK(chooseOverlay(t.path()) == QDir(t.path()).filePath("overlay.zarr"));
    QDir(t.path()).mkdir("overlay_vc3d.zarr");
    CHECK(chooseOverlay(t.path()) == QDir(t.path()).filePath("overlay_vc3d.zarr"));
}

static void testPlacementGuard()
{
    QTemporaryDir t;
    const QDir d(t.path());
    CHECK(overlayPlacementProblem(t.path()).isEmpty());  // no .zattrs
    auto write = [&](const QByteArray& j) {
        QFile f(d.filePath(".zattrs"));
        f.open(QIODevice::WriteOnly | QIODevice::Truncate);
        f.write(j);
    };
    write(R"({"multiscales":[{"datasets":[{"path":"0","coordinateTransformations":[{"type":"scale","scale":[7.91,7.91,7.91]}]}]}]})");
    CHECK(overlayPlacementProblem(t.path()).isEmpty());
    write(R"({"multiscales":[{"datasets":[{"path":"0","coordinateTransformations":[{"type":"scale","scale":[7.91,7.91,7.91]},{"type":"translation","translation":[0,0,0]}]}]}]})");
    CHECK(overlayPlacementProblem(t.path()).isEmpty());
    write(R"({"multiscales":[{"datasets":[{"path":"0","coordinateTransformations":[{"type":"scale","scale":[7.91,7.91,7.91]},{"type":"translation","translation":[33411.84,20249.6,5062.4]}]}]}]})");
    CHECK(overlayPlacementProblem(t.path()).contains("translation"));
    // Zarr v3: OME attributes live in zarr.json "attributes".
    QTemporaryDir t3;
    {
        QFile f(QDir(t3.path()).filePath("zarr.json"));
        f.open(QIODevice::WriteOnly);
        f.write(R"({"zarr_format":3,"node_type":"group","attributes":{"multiscales":[{"datasets":[{"path":"0","coordinateTransformations":[{"type":"translation","translation":[1,0,0]}]}]}]}})");
    }
    CHECK(overlayPlacementProblem(t3.path()).contains("translation"));
}

static void testProjectEntries()
{
    QTemporaryDir t;
    const QDir d(t.path());
    for (const char* n : {"segA-1", "segA-2", "segB-1", "user.zarr"})
        d.mkdir(n);
    const auto P = [&](const char* n) { return d.filePath(n); };
    const QString gone = d.filePath("segB-0-deleted");  // never created
    const QString goneUntagged = d.filePath("user-deleted.zarr");
    CHECK(segmentTag("segA") == "sheet_check_segment:segA");
    CHECK(overlayEntryTags("segA") == QStringList({"sheet_check", "sheet_check_segment:segA"}));
    const std::vector<ProjectEntry> entries = {
        {P("user.zarr"), {}},                              // base volume: never touched
        {goneUntagged, {"normal3d"}},                      // missing but not ours: never touched
        {P("segA-1"), overlayEntryTags("segA")},           // same segment: replaced
        {P("segB-1"), overlayEntryTags("segB")},           // other segment, exists: kept
        {gone, overlayEntryTags("segB")},                  // other segment, missing: pruned
        {P("segA-2"), overlayEntryTags("segA")},           // the new location itself: kept
    };
    const QStringList stale = staleOverlayEntries(entries, "segA", P("segA-2"));
    CHECK(stale == QStringList({P("segA-1"), gone}));
    // Second run for segB: its existing entry is replaced, segA's current one kept.
    d.mkdir("segB-2");
    CHECK(staleOverlayEntries(entries, "segB", P("segB-2")) == QStringList({P("segB-1"), gone}));
    CHECK(staleOverlayEntries({}, "segA", P("segA-2")).isEmpty());
}

static void testGolden(const QString& dir)
{
    // Fixture v1.4 (Amendments 7 and 10): example_outputs.py region A, full-frame overlay, 51 clusters.
    const auto r = parseReportFile(QDir(dir).filePath("report.json"));
    if (!r.report) {
        std::fprintf(stderr, "golden parse error: %s\n", qPrintable(r.error));
        ++failures;
        return;
    }
    CHECK(r.report->contract == "v1" && r.report->status == "ok");
    CHECK(r.report->regionOriginZyx == (Zyx{4224, 2560, 640}));
    CHECK(r.report->regionShapeZyx == (Zyx{384, 384, 384}));
    CHECK(r.report->overlayOriginZyx == (Zyx{3712, 2176, 384}));   // A10.2
    CHECK(r.report->overlayShapeZyx == (Zyx{1408, 896, 1152}));
    CHECK(r.report->pairsFlagged == 92);
    int suspect = 0, wrong = 0;
    for (const auto& c : r.report->clusters)
        (c.kind == "suspect_join" ? suspect : wrong)++;
    CHECK(suspect == 30 && wrong == 21);
    int outside = 0, outsideAnalysis = 0;
    for (const auto& c : r.report->clusters) {
        outside += insideRegion(*r.report, c) ? 0 : 1;
        for (int i = 0; i < 3; ++i)
            if (c.centroidZyx[i] < r.report->regionOriginZyx[i] ||
                c.centroidZyx[i] >= r.report->regionOriginZyx[i] + r.report->regionShapeZyx[i]) {
                ++outsideAnalysis;
                break;
            }
    }
    CHECK(outside == 0);            // A10.2: every cluster centre lies inside overlay_region
    CHECK(outsideAnalysis == 26);   // ...though 26 lie outside the 384^3 analysis region, as in v1.1 (R7)
    const QString ov = chooseOverlay(dir);
    CHECK(QFileInfo(ov).fileName() == "overlay.zarr");
    CHECK(overlayPlacementProblem(ov).isEmpty());  // A4.1: no translation, the guard must not fire
    // First cluster's jump target, zyx reversed (A4.3).
    const auto& c0 = r.report->clusters.front();
    const auto xyz = toVc3dXyz(c0.centroidZyx);
    CHECK(xyz[0] == float(c0.centroidZyx[2]) && xyz[2] == float(c0.centroidZyx[0]));
    std::printf("golden: %s contract=%s status=%s clusters=%zu (suspect %d, wrong_turn %d) pairs_flagged=%lld overlay=%s guard=%s\n",
                qPrintable(dir), qPrintable(r.report->contract), qPrintable(r.report->status),
                r.report->clusters.size(), suspect, wrong, static_cast<long long>(r.report->pairsFlagged),
                qPrintable(QFileInfo(ov).fileName()), overlayPlacementProblem(ov).isEmpty() ? "silent" : "FIRED");
}

int main(int argc, char** argv)
{
    QCoreApplication app(argc, argv);
    testInvocation();
    testJoinSpec();
    testSwap();
    testParseSchema();
    testParseErrors();
    testOverlayRegion();
    testChooseOverlay();
    testPlacementGuard();
    testProjectEntries();
    if (argc > 1)
        testGolden(QString::fromLocal8Bit(argv[1]));
    std::printf("%s (%d failures)\n", failures ? "FAILED" : "OK", failures);
    return failures ? 1 : 0;
}
