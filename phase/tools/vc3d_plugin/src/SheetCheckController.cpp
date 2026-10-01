#include "SheetCheckController.hpp"

#include <QAction>
#include <QDateTime>
#include <QDir>
#include <QDockWidget>
#include <QFileDialog>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QListWidget>
#include <QVBoxLayout>
#include <QMainWindow>
#include <QMessageBox>
#include <QProcess>
#include <QStandardPaths>

#include <iostream>

namespace sheetcheck {

namespace {
constexpr int kClusterIndexRole = Qt::UserRole + 1;

void log(const QString& msg)
{
    // Plain stdout line so headless runs can be checked from the log.
    std::cout << "vc.sheet_check: " << msg.toStdString() << std::endl;
}
}  // namespace

SheetCheckController::SheetCheckController(Host host, QObject* parent)
    : QObject(parent), _host(std::move(host))
{
    _action = new QAction(tr("Sheet check"), this);
    _action->setObjectName(QStringLiteral("actionSheetCheck"));
    _action->setStatusTip(tr("Run vc_sheet_check on the active segment and current volume"));
    connect(_action, &QAction::triggered, this, &SheetCheckController::run);
    _joinAction = new QAction(tr("Sheet check (joins)"), this);
    _joinAction->setObjectName(QStringLiteral("actionSheetCheckJoins"));
    _joinAction->setStatusTip(tr("Run vc_sheet_check's join mode on a region, from a join spec"));
    connect(_joinAction, &QAction::triggered, this, &SheetCheckController::runJoin);
    log(QStringLiteral("action registered"));
}

QString SheetCheckController::resolveProgram()
{
    const QString env = qEnvironmentVariable("VC_SHEET_CHECK");
    if (!env.isEmpty())
        return env;
    return QStandardPaths::findExecutable(QStringLiteral("vc_sheet_check"));
}

void SheetCheckController::run()
{
    if (_proc) {
        _host.status(tr("Sheet check is already running."), 4000);
        return;
    }
    const QString segment = _host.segmentPath();
    const QString volume = _host.volumePath();
    if (segment.isEmpty() || volume.isEmpty())
        return fail(tr("Select a segment and load a volume first."));
    QString axisReason;
    const QString axis = _host.axisFile(&axisReason);
    if (axis.isEmpty())
        return fail(tr("Segment mode disabled: no umbilicus for --axis-file (contract A5.3): %1").arg(axisReason));
    const QString program = resolveProgram();
    if (program.isEmpty())
        return fail(tr("vc_sheet_check not found. Put it on PATH or set VC_SHEET_CHECK."));
    const QString outDir = makeOutDir(QFileInfo(segment).fileName());
    if (outDir.isEmpty())
        return;
    _segmentIdAtStart = _host.segmentId();
    start(buildInvocation(program, segment, volume, outDir, axis), _segmentIdAtStart);
}

void SheetCheckController::runJoin()
{
    if (_proc) {
        _host.status(tr("Sheet check is already running."), 4000);
        return;
    }
    QString specPath = qEnvironmentVariable("VC_SHEET_CHECK_JOIN");
    if (specPath.isEmpty() && qEnvironmentVariableIsEmpty("VC_SHEET_CHECK_NO_DIALOGS"))
        specPath = QFileDialog::getOpenFileName(_host.dockHost, tr("Join spec"), QString(),
                                                tr("Join spec (*.json)"));
    if (specPath.isEmpty())
        return fail(tr("Join mode needs a join spec (a region, its patches and rel.csv)."));
    const JoinSpecResult parsed = parseJoinSpecFile(specPath);
    if (!parsed.spec)
        return fail(parsed.error);
    const JoinSpec& spec = *parsed.spec;
    const QString volume = spec.volume.isEmpty() ? _host.volumePath() : spec.volume;
    if (volume.isEmpty())
        return fail(tr("The join spec names no volume and none is loaded."));
    const QString program = resolveProgram();
    if (program.isEmpty())
        return fail(tr("vc_sheet_check not found. Put it on PATH or set VC_SHEET_CHECK."));
    const QString key = joinEntryKey(spec);
    const QString outDir = makeOutDir(QString(key).replace(QLatin1Char(':'), QLatin1Char('_')));
    if (outDir.isEmpty())
        return;
    _segmentIdAtStart = _host.segmentId();  // for jump-to only; may be empty in join mode
    start(buildJoinInvocation(program, spec, volume, outDir), key);
}

QString SheetCheckController::makeOutDir(const QString& name)
{
    // Outputs go to the cache, never into the segment or volume directory.
    const QString outDir = QDir(QStandardPaths::writableLocation(QStandardPaths::CacheLocation))
        .filePath(QStringLiteral("sheet_check/%1-%2")
                      .arg(name, QDateTime::currentDateTimeUtc().toString(QStringLiteral("yyyyMMddTHHmmsszzz"))));
    if (!QDir().mkpath(outDir)) {
        fail(tr("Cannot create %1").arg(outDir));
        return {};
    }
    return outDir;
}

void SheetCheckController::start(const Invocation& inv, const QString& entryKey)
{
    _inv = inv;
    _entryKey = entryKey;
    _failed = false;
    _proc = new QProcess(this);
    _proc->setProcessChannelMode(QProcess::MergedChannels);
    connect(_proc, &QProcess::readyRead, this, [this] {
        if (_proc)
            std::cout << _proc->readAll().toStdString() << std::flush;
    });
    connect(_proc, &QProcess::finished, this,
            [this](int code, QProcess::ExitStatus st) { onFinished(code, static_cast<int>(st)); });
    connect(_proc, &QProcess::errorOccurred, this, [this](QProcess::ProcessError e) {
        if (e == QProcess::FailedToStart) {
            _proc->deleteLater();
            fail(tr("Could not start %1").arg(_inv.program));
            emit finished(false);
        }
    });
    log(QStringLiteral("start %1 %2").arg(_inv.program, _inv.arguments.join(' ')));
    _host.status(tr("Sheet check running..."), 0);
    _proc->start(_inv.program, _inv.arguments);
}

void SheetCheckController::onFinished(int exitCode, int exitStatus)
{
    _proc->deleteLater();
    if (exitStatus != QProcess::NormalExit || exitCode != 0) {
        // A4.2: non-zero exit is failure whatever files exist; show the tool's own message if it wrote one.
        QString detail;
        QFile f(_inv.reportPath);
        if (f.open(QIODevice::ReadOnly))
            detail = QJsonDocument::fromJson(f.readAll()).object().value("error").toString();
        fail(detail.isEmpty() ? tr("vc_sheet_check exited with code %1").arg(exitCode)
                              : tr("vc_sheet_check exited with code %1: %2").arg(exitCode).arg(detail));
        emit finished(false);
        return;
    }

    const ParseResult parsed = parseReportFile(_inv.reportPath);
    if (!parsed.report) {
        fail(parsed.error);
        emit finished(false);
        return;
    }
    _report = *parsed.report;
    const QString overlay = chooseOverlay(_inv.outDir);
    log(QStringLiteral("report %1 contract=%2 clusters=%3 pairs_flagged=%4 overlay=%5")
            .arg(_inv.reportPath, _report.contract).arg(_report.clusters.size())
            .arg(_report.pairsFlagged).arg(overlay));

    QString err;
    const QString placement = overlay.isEmpty() ? QString() : overlayPlacementProblem(overlay);
    QString volId;
    if (!overlay.isEmpty() && placement.isEmpty()) {
        const QStringList stale = staleOverlayEntries(_host.volumeEntries(), _entryKey, overlay);
        if (!stale.isEmpty()) {
            _host.removeVolumeEntries(stale);
            log(QStringLiteral("removed project entries: %1").arg(stale.join(QStringLiteral(", "))));
        }
        volId = _host.attachVolume(overlay, overlayEntryTags(_entryKey), &err);
    }
    if (overlay.isEmpty()) {
        fail(tr("No overlay.zarr in %1").arg(_inv.outDir));
    } else if (!placement.isEmpty()) {
        fail(tr("Overlay not loaded: %1").arg(placement));
    } else if (volId.isEmpty()) {
        fail(tr("Overlay not loaded: %1").arg(err));
    } else if (!_host.showOverlay(volId)) {
        fail(tr("Overlay volume %1 attached but could not be shown").arg(volId));
    } else {
        log(QStringLiteral("overlay layer %1").arg(volId));
    }
    showReport(_report);  // the list is useful even if the overlay failed
    _host.status(tr("Sheet check: %n flagged cluster(s)", nullptr,
                    static_cast<int>(_report.clusters.size())), 8000);
    emit finished(!_failed);
}

void SheetCheckController::ensureDock()
{
    if (_dock)
        return;
    _dock = new QDockWidget(tr("Sheet check"), _host.dockHost);
    _dock->setObjectName(QStringLiteral("sheetCheckDock"));
    auto* body = new QWidget(_dock);
    auto* layout = new QVBoxLayout(body);
    layout->setContentsMargins(0, 0, 0, 0);
    _list = new QListWidget(body);
    _list->setToolTip(tr("Double-click to jump to a cluster"));
    layout->addWidget(_list, 1);
    // Contract Amendment 3 A3.1: required wording for any viewer text.
    auto* note = new QLabel(tr("Flags mark where the index changes, not where it is doubtful. "
                               "\"switch\" is the switch score, not an error estimate."), body);
    note->setWordWrap(true);
    layout->addWidget(note);
    _dock->setWidget(body);
    _host.dockHost->addDockWidget(Qt::RightDockWidgetArea, _dock);
    connect(_list, &QListWidget::itemActivated, this, &SheetCheckController::jumpToItem);
}

void SheetCheckController::showReport(const Report& report)
{
    ensureDock();
    _list->clear();
    for (std::size_t i = 0; i < report.clusters.size(); ++i) {
        auto* item = new QListWidgetItem(describe(report, report.clusters[i]), _list);
        item->setData(kClusterIndexRole, static_cast<int>(i));
    }
    if (report.clusters.empty())
        new QListWidgetItem(tr("No flagged clusters"), _list);
    _dock->show();
    _dock->raise();
    log(QStringLiteral("dock rows=%1").arg(_list->count()));
}

void SheetCheckController::jumpToItem(QListWidgetItem* item)
{
    const QVariant v = item ? item->data(kClusterIndexRole) : QVariant();
    if (!v.isValid())
        return;
    const Cluster& c = _report.clusters.at(static_cast<std::size_t>(v.toInt()));
    const auto xyz = toVc3dXyz(c.centroidZyx);
    _host.jumpTo(xyz, std::nullopt, _segmentIdAtStart);  // contract clusters carry no normal
    log(QStringLiteral("jump %1 xyz=%2,%3,%4").arg(c.id).arg(xyz[0]).arg(xyz[1]).arg(xyz[2]));
}

void SheetCheckController::fail(const QString& message)
{
    _failed = true;
    log(QStringLiteral("error: ") + message);
    _host.status(message, 8000);
    if (qEnvironmentVariableIsEmpty("VC_SHEET_CHECK_NO_DIALOGS"))
        QMessageBox::warning(_host.dockHost, tr("Sheet check"), message);
}

}  // namespace sheetcheck
