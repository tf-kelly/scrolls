#include "SheetCheckCore.hpp"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

#include <cmath>

namespace sheetcheck {

namespace {

constexpr auto kContractVersion = "v1";

std::optional<Zyx> vec3(const QJsonValue& v)
{
    const QJsonArray a = v.toArray();
    if (a.size() != 3)
        return std::nullopt;
    Zyx out{};
    for (int i = 0; i < 3; ++i) {
        if (!a[i].isDouble() || !std::isfinite(a[i].toDouble()))
            return std::nullopt;
        out[i] = a[i].toDouble();
    }
    return out;
}

ParseResult fail(const QString& msg) { return {std::nullopt, msg}; }

}  // namespace

Invocation buildInvocation(const QString& cliProgram,
                           const QString& segmentPath,
                           const QString& volumePath,
                           const QString& outDir,
                           const QString& axisFile)
{
    Invocation inv;
    inv.program = cliProgram;
    inv.arguments = {QStringLiteral("--segment"), segmentPath,
                     QStringLiteral("--volume"), volumePath,
                     QStringLiteral("--out"), outDir};
    if (!axisFile.isEmpty())
        inv.arguments << QStringLiteral("--axis-file") << axisFile;
    inv.outDir = outDir;
    inv.reportPath = QDir(outDir).filePath(QStringLiteral("report.json"));
    return inv;
}

namespace {

JoinSpecResult joinFail(const QString& msg) { return {std::nullopt, msg}; }

bool isWholeNumber(const QJsonValue& v)
{
    return v.isDouble() && std::isfinite(v.toDouble()) && v.toDouble() == std::floor(v.toDouble());
}

}  // namespace

JoinSpecResult parseJoinSpec(const QByteArray& json, const QString& baseDir)
{
    QJsonParseError err{};
    const QJsonDocument doc = QJsonDocument::fromJson(json, &err);
    if (err.error != QJsonParseError::NoError)
        return joinFail(QStringLiteral("join spec is not valid JSON: %1").arg(err.errorString()));
    if (!doc.isObject())
        return joinFail(QStringLiteral("join spec top level is not an object"));
    const QJsonObject root = doc.object();
    const QDir base(baseDir);
    const auto path = [&base](const QJsonValue& v) {
        return v.toString().isEmpty() ? QString() : QDir::cleanPath(base.absoluteFilePath(v.toString()));
    };

    JoinSpec s;
    const QJsonArray region = root.value("region").toArray();
    if (region.size() != 6)
        return joinFail(QStringLiteral("join spec needs \"region\": [z, y, x, nz, ny, nx]"));
    for (int i = 0; i < 6; ++i) {
        if (!isWholeNumber(region[i]) || (i < 3 ? region[i].toDouble() < 0 : region[i].toDouble() <= 0))
            return joinFail(QStringLiteral("join spec \"region\" needs whole numbers, origin >= 0 and size > 0"));
        s.region[i] = static_cast<qint64>(region[i].toDouble());
    }
    const QJsonValue patches = root.value("patches");
    for (const QJsonValue& p : patches.isArray() ? patches.toArray() : QJsonArray{patches})
        if (!p.toString().isEmpty())
            s.patches << path(p);
    if (s.patches.isEmpty())
        return joinFail(QStringLiteral("join spec needs \"patches\" (zip or directory of patch_N/ folders)"));
    s.rel = path(root.value("rel"));
    if (s.rel.isEmpty())
        return joinFail(QStringLiteral("join spec needs \"rel\" (pipeline9 rel.csv)"));
    // A local volume resolves against the spec; a URL is passed through.
    const QString volume = root.value("volume").toString();
    s.volume = volume.contains(QStringLiteral("://")) ? volume : path(root.value("volume"));
    s.wrapIndex = path(root.value("wrap_index"));
    s.patchTable = path(root.value("patch_table"));
    s.axisFile = path(root.value("axis_file"));
    s.riskModel = path(root.value("risk_model"));
    if (root.contains("scan_shape")) {
        const QJsonArray a = root.value("scan_shape").toArray();
        if (a.size() != 3)
            return joinFail(QStringLiteral("join spec \"scan_shape\" needs [z, y, x]"));
        std::array<qint64, 3> shape{};
        for (int i = 0; i < 3; ++i) {
            if (!isWholeNumber(a[i]) || a[i].toDouble() <= 0)
                return joinFail(QStringLiteral("join spec \"scan_shape\" needs positive whole numbers"));
            shape[i] = static_cast<qint64>(a[i].toDouble());
        }
        s.scanShape = shape;
    }
    return {s, {}};
}

JoinSpecResult parseJoinSpecFile(const QString& path)
{
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly))
        return joinFail(QStringLiteral("cannot read join spec %1").arg(path));
    return parseJoinSpec(f.readAll(), QFileInfo(path).absolutePath());
}

Invocation buildJoinInvocation(const QString& cliProgram,
                               const JoinSpec& spec,
                               const QString& volumePath,
                               const QString& outDir)
{
    Invocation inv;
    inv.program = cliProgram;
    inv.arguments << QStringLiteral("--region");
    for (qint64 v : spec.region)
        inv.arguments << QString::number(v);
    inv.arguments << QStringLiteral("--patches") << spec.patches
                  << QStringLiteral("--rel") << spec.rel
                  << QStringLiteral("--volume") << (spec.volume.isEmpty() ? volumePath : spec.volume)
                  << QStringLiteral("--out") << outDir;
    if (!spec.wrapIndex.isEmpty())
        inv.arguments << QStringLiteral("--wrap-index") << spec.wrapIndex;
    if (!spec.patchTable.isEmpty())
        inv.arguments << QStringLiteral("--patch-table") << spec.patchTable;
    if (!spec.axisFile.isEmpty())
        inv.arguments << QStringLiteral("--axis-file") << spec.axisFile;
    if (!spec.riskModel.isEmpty())
        inv.arguments << QStringLiteral("--risk-model") << spec.riskModel;
    if (spec.scanShape) {
        inv.arguments << QStringLiteral("--scan-shape");
        for (qint64 v : *spec.scanShape)
            inv.arguments << QString::number(v);
    }
    inv.outDir = outDir;
    inv.reportPath = QDir(outDir).filePath(QStringLiteral("report.json"));
    return inv;
}

QString joinEntryKey(const JoinSpec& spec)
{
    QStringList parts;
    for (qint64 v : spec.region)
        parts << QString::number(v);
    return QStringLiteral("region:") + parts.join(QLatin1Char('_'));
}

ParseResult parseReport(const QByteArray& json)
{
    QJsonParseError err{};
    const QJsonDocument doc = QJsonDocument::fromJson(json, &err);
    if (err.error != QJsonParseError::NoError)
        return fail(QStringLiteral("report.json is not valid JSON: %1").arg(err.errorString()));
    if (!doc.isObject())
        return fail(QStringLiteral("report.json top level is not an object"));
    const QJsonObject root = doc.object();

    Report r;
    r.contract = root.value("contract").toString();
    if (r.contract != QLatin1String(kContractVersion))
        return fail(QStringLiteral("report.json contract is \"%1\", expected \"%2\"")
                        .arg(r.contract, kContractVersion));
    r.git = root.value("git").toString();
    r.status = root.value("status").toString();
    if (!r.status.isEmpty() && r.status != QLatin1String("ok"))
        return fail(QStringLiteral("vc_sheet_check reported status \"%1\": %2")
                        .arg(r.status, root.value("error").toString()));

    const QJsonObject region = root.value("region").toObject();
    const auto origin = vec3(region.value("origin_zyx"));
    const auto shape = vec3(region.value("shape_zyx"));
    if (!origin || !shape)
        return fail(QStringLiteral("report.json region needs origin_zyx and shape_zyx"));
    r.regionOriginZyx = *origin;
    r.regionShapeZyx = *shape;
    r.overlayOriginZyx = *origin;
    r.overlayShapeZyx = *shape;
    if (root.contains("overlay_region")) {
        const QJsonObject ovr = root.value("overlay_region").toObject();
        const auto ovo = vec3(ovr.value("origin_zyx"));
        const auto ovs = vec3(ovr.value("shape_zyx"));
        if (!ovo || !ovs)
            return fail(QStringLiteral("report.json overlay_region needs origin_zyx and shape_zyx"));
        r.overlayOriginZyx = *ovo;
        r.overlayShapeZyx = *ovs;
    }
    r.pairsFlagged = root.value("counts").toObject().value("pairs_flagged").toInteger(0);

    const QJsonValue cv = root.value("clusters");
    if (!cv.isArray())
        return fail(QStringLiteral("report.json has no \"clusters\" array"));
    const QJsonArray arr = cv.toArray();
    for (qsizetype i = 0; i < arr.size(); ++i) {
        const QJsonObject o = arr[i].toObject();
        Cluster c;
        if (!o.value("id").isDouble())
            return fail(QStringLiteral("cluster %1 has no integer id").arg(i));
        c.id = o.value("id").toInteger();
        c.kind = o.value("kind").toString();
        if (c.kind != QLatin1String("suspect_join") && c.kind != QLatin1String("wrong_turn"))
            return fail(QStringLiteral("cluster %1 has unknown kind \"%2\"").arg(c.id).arg(c.kind));
        const auto centroid = vec3(o.value("centroid_zyx"));
        if (!centroid)
            return fail(QStringLiteral("cluster %1 has no valid centroid_zyx").arg(c.id));
        c.centroidZyx = *centroid;
        const QJsonArray bb = o.value("bbox_zyx").toArray();
        const auto lo = bb.size() == 2 ? vec3(bb[0]) : std::nullopt;
        const auto hi = bb.size() == 2 ? vec3(bb[1]) : std::nullopt;
        if (!lo || !hi)
            return fail(QStringLiteral("cluster %1 has no valid bbox_zyx").arg(c.id));
        c.bboxLoZyx = *lo;
        c.bboxHiZyx = *hi;
        c.nPairs = o.value("n_pairs").toInteger(0);
        c.nPatches = o.value("n_patches").toInteger(0);
        c.areaCm2 = o.value("area_cm2").toDouble(0.0);
        if (o.value("max_risk").isDouble())
            c.maxRisk = o.value("max_risk").toDouble();
        r.clusters.push_back(std::move(c));
    }
    return {std::move(r), {}};
}

ParseResult parseReportFile(const QString& reportPath)
{
    QFile f(reportPath);
    if (!f.open(QIODevice::ReadOnly))
        return fail(QStringLiteral("cannot read %1: %2").arg(reportPath, f.errorString()));
    return parseReport(f.readAll());
}

QString chooseOverlay(const QString& outDir)
{
    const QDir d(outDir);
    for (const auto* name : {"overlay_vc3d.zarr", "overlay.zarr"}) {
        const QString p = d.filePath(QString::fromLatin1(name));
        if (QFileInfo(p).isDir())
            return QDir::cleanPath(QFileInfo(p).absoluteFilePath());
    }
    return {};
}

QString overlayPlacementProblem(const QString& overlayDir)
{
    // OME attributes: .zattrs (Zarr v2) or zarr.json "attributes" (Zarr v3).
    QJsonObject attrs;
    QFile v2(QDir(overlayDir).filePath(QStringLiteral(".zattrs")));
    QFile v3(QDir(overlayDir).filePath(QStringLiteral("zarr.json")));
    if (v2.open(QIODevice::ReadOnly))
        attrs = QJsonDocument::fromJson(v2.readAll()).object();
    else if (v3.open(QIODevice::ReadOnly))
        attrs = QJsonDocument::fromJson(v3.readAll()).object().value("attributes").toObject();
    else
        return {};  // plain zarr without OME metadata: no translation
    const QJsonArray datasets =
        attrs.value("multiscales").toArray().first().toObject().value("datasets").toArray();
    for (const QJsonValue& ds : datasets) {
        for (const QJsonValue& t : ds.toObject().value("coordinateTransformations").toArray()) {
            const QJsonObject o = t.toObject();
            if (o.value("type").toString() != QLatin1String("translation"))
                continue;
            for (const QJsonValue& v : o.value("translation").toArray()) {
                if (v.toDouble() != 0.0)
                    return QStringLiteral(
                        "%1 has a non-zero OME translation, which VC3D cannot place. "
                        "The CLI should also write overlay_vc3d.zarr (zero translation, scan frame).")
                        .arg(overlayDir);
            }
        }
    }
    return {};
}

QString segmentTag(const QString& segmentId)
{
    return QStringLiteral("sheet_check_segment:") + segmentId;
}

QStringList overlayEntryTags(const QString& segmentId)
{
    return {QString::fromLatin1(kEntryTag), segmentTag(segmentId)};
}

QStringList staleOverlayEntries(const std::vector<ProjectEntry>& entries,
                                const QString& segmentId,
                                const QString& newLocation)
{
    QStringList out;
    for (const ProjectEntry& e : entries) {
        if (!e.tags.contains(QString::fromLatin1(kEntryTag)) || e.location == newLocation)
            continue;
        if (e.tags.contains(segmentTag(segmentId)) || !QFileInfo(e.location).isDir())
            out << e.location;
    }
    return out;
}

std::array<float, 3> toVc3dXyz(const Zyx& zyx)
{
    return {static_cast<float>(zyx[2]), static_cast<float>(zyx[1]),
            static_cast<float>(zyx[0])};
}

bool insideRegion(const Report& r, const Cluster& c)
{
    for (int i = 0; i < 3; ++i) {
        const double v = c.centroidZyx[i];
        if (v < r.overlayOriginZyx[i] || v >= r.overlayOriginZyx[i] + r.overlayShapeZyx[i])
            return false;
    }
    return true;
}

QString describe(const Report& r, const Cluster& c)
{
    return insideRegion(r, c) ? describe(c) : describe(c) + QStringLiteral("  [outside overlay region]");
}

QString describe(const Cluster& c)
{
    QString s = QStringLiteral("#%1 %2  z=%3 y=%4 x=%5  pairs=%6 patches=%7  %8 cm2")
                    .arg(c.id)
                    .arg(c.kind)
                    .arg(c.centroidZyx[0], 0, 'f', 0)
                    .arg(c.centroidZyx[1], 0, 'f', 0)
                    .arg(c.centroidZyx[2], 0, 'f', 0)
                    .arg(c.nPairs)
                    .arg(c.nPatches)
                    .arg(c.areaCm2, 0, 'f', 3);
    if (c.maxRisk)
        s += QStringLiteral("  switch=%1").arg(*c.maxRisk, 0, 'f', 2);
    return s;
}

}  // namespace sheetcheck
