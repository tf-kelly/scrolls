// Headless test of the menu handler (Tools -> Sheet check (joins)), offscreen Qt, no VC3D.
// Builds the Tools menu as villa's hook does, triggers the join action from it, and lets the
// controller run the REAL vc_sheet_check (join mode, contract A4.2 region form) on the join spec.
// The host is a stub that records what VC3D would be asked to do.
// Usage: test_sheet_check_controller JOIN_SPEC   (env VC_SHEET_CHECK = the real CLI)
#include "SheetCheckController.hpp"

#include <QApplication>
#include <QDir>
#include <QFileInfo>
#include <QListWidget>
#include <QMainWindow>
#include <QMenu>
#include <QMenuBar>
#include <QTimer>

#include <iostream>

using namespace sheetcheck;

namespace {
int failures = 0;
void check(bool ok, const std::string& what)
{
    std::cout << (ok ? "PASS " : "FAIL ") << what << std::endl;
    if (!ok)
        ++failures;
}
}  // namespace

int main(int argc, char** argv)
{
    if (argc != 2) {
        std::cerr << "usage: test_sheet_check_controller JOIN_SPEC" << std::endl;
        return 2;
    }
    qputenv("QT_QPA_PLATFORM", "offscreen");
    qputenv("VC_SHEET_CHECK_NO_DIALOGS", "1");
    qputenv("VC_SHEET_CHECK_JOIN", argv[1]);
    QApplication app(argc, argv);
    QMainWindow win;

    QString attached, shownId, jumpSegment;
    QStringList attachedTags;
    std::optional<std::array<float, 3>> jumped;
    Host host;
    host.dockHost = &win;
    host.segmentPath = [] { return QString(); };  // join mode needs no active segment
    host.segmentId = [] { return QString(); };
    host.volumePath = [] { return QString(); };   // the spec names the volume
    host.axisFile = [](QString* reason) {
        if (reason)
            *reason = QStringLiteral("stub host");
        return QString();
    };
    host.attachVolume = [&](const QString& path, const QStringList& tags, QString*) {
        attached = path;
        attachedTags = tags;
        return QStringLiteral("vol1");
    };
    host.volumeEntries = [] { return std::vector<ProjectEntry>{}; };
    host.removeVolumeEntries = [](const QStringList&) {};
    host.showOverlay = [&](const QString& id) {
        shownId = id;
        return true;
    };
    host.jumpTo = [&](const std::array<float, 3>& xyz, const std::optional<std::array<float, 3>>&, const QString& seg) {
        jumped = xyz;
        jumpSegment = seg;
    };
    host.status = [](const QString& m, int) { std::cout << "status: " << m.toStdString() << std::endl; };

    SheetCheckController controller(host, &win);
    QMenu* tools = win.menuBar()->addMenu(QStringLiteral("Tools"));  // as MenuActionController does
    tools->addAction(controller.action());
    tools->addAction(controller.joinAction());

    QAction* joinItem = nullptr;
    for (QAction* a : tools->actions())
        if (a->objectName() == QLatin1String("actionSheetCheckJoins"))
            joinItem = a;
    check(joinItem != nullptr && joinItem->text() == QLatin1String("Sheet check (joins)"),
          "Tools menu holds \"Sheet check (joins)\"");
    if (!joinItem)
        return 1;

    bool done = false, ok = false;
    QObject::connect(&controller, &SheetCheckController::finished, &app, [&](bool o) {
        done = true;
        ok = o;
        app.quit();
    });
    QTimer::singleShot(30 * 60 * 1000, &app, [&] { app.quit(); });  // 30 min cap
    QTimer::singleShot(0, joinItem, &QAction::trigger);               // the menu click
    app.exec();

    check(done, "run finished (finished signal within 30 min)");
    check(ok, "run succeeded (exit 0, report parsed, overlay attached and shown)");
    const JoinSpecResult spec = parseJoinSpecFile(QString::fromLocal8Bit(argv[1]));
    check(spec.spec.has_value(), "join spec parses");
    if (!done || !spec.spec)
        return 1;

    const QString outDir = QFileInfo(attached).absolutePath();
    const ParseResult rep = parseReportFile(QDir(outDir).filePath(QStringLiteral("report.json")));
    check(rep.report.has_value(), "report.json parses (contract v1)");
    check(QFileInfo(attached).isDir() && attached == chooseOverlay(outDir), "attached the overlay the CLI wrote");
    check(attachedTags.contains(QString::fromLatin1(kEntryTag))
              && attachedTags.contains(segmentTag(joinEntryKey(*spec.spec))),
          "overlay tagged sheet_check + " + segmentTag(joinEntryKey(*spec.spec)).toStdString());
    check(shownId == QLatin1String("vol1"), "overlay shown");
    if (rep.report) {
        const auto& r = *rep.report;
        const auto& g = spec.spec->region;
        check(r.regionOriginZyx == Zyx{double(g[0]), double(g[1]), double(g[2])}
                  && r.regionShapeZyx == Zyx{double(g[3]), double(g[4]), double(g[5])},
              "report region equals the spec's region (join mode ran on it)");
        auto* list = win.findChild<QListWidget*>();
        const int expectRows = r.clusters.empty() ? 1 : static_cast<int>(r.clusters.size());
        check(list && list->count() == expectRows,
              "dock lists " + std::to_string(expectRows) + " row(s) for " + std::to_string(r.clusters.size()) + " cluster(s)");
        if (list && !r.clusters.empty()) {
            emit list->itemActivated(list->item(0));
            const auto want = toVc3dXyz(r.clusters[0].centroidZyx);
            check(jumped && *jumped == want, "jump-to on row 0 goes to cluster 0's centroid (x, y, z)");
        }
    }
    std::cout << (failures ? "FAILED " : "ALL PASS ") << failures << " failure(s)" << std::endl;
    return failures ? 1 : 0;
}
