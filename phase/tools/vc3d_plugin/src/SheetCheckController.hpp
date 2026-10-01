#pragma once

// Tools -> Sheet check. Runs vc_sheet_check on the active segment and the
// current volume, attaches the overlay zarr it writes as an overlay volume,
// and lists flagged clusters in a dock with jump-to. No analysis here.
// Tools -> Sheet check (joins) runs the checker's join mode (contract A4.2
// region form) from a join spec instead; overlay and dock are shared.

#include "SheetCheckCore.hpp"

#include <QObject>
#include <QPointer>
#include <QString>

#include <array>
#include <functional>
#include <optional>

class QAction;
class QDockWidget;
class QListWidget;
class QListWidgetItem;
class QMainWindow;
class QProcess;

namespace sheetcheck {

// Everything the controller needs from VC3D, supplied by the menu owner so
// the controller never reaches into CWindow.
struct Host {
    QMainWindow* dockHost{nullptr};
    std::function<QString()> segmentPath;   // empty when no segment is active
    std::function<QString()> segmentId;
    std::function<QString()> volumePath;    // empty when no volume is loaded
    // The scan's umbilicus for "--axis-file" (contract A5.3). Empty, with
    // *reason set, when none can be resolved: segment mode is then disabled.
    std::function<QString(QString* reason)> axisFile;
    // Attach a local zarr to the open project with these tags; return its
    // volume id, or an empty string with *error set.
    std::function<QString(const QString& path, const QStringList& tags, QString* error)> attachVolume;
    std::function<std::vector<ProjectEntry>()> volumeEntries;  // the project's volume entries
    std::function<void(const QStringList& locations)> removeVolumeEntries;
    std::function<bool(const QString& volumeId)> showOverlay;
    std::function<void(const std::array<float, 3>& xyz,
                       const std::optional<std::array<float, 3>>& normalXyz,
                       const QString& segmentId)> jumpTo;
    std::function<void(const QString& message, int timeoutMs)> status;
};

class SheetCheckController : public QObject
{
    Q_OBJECT

public:
    SheetCheckController(Host host, QObject* parent);
    QAction* action() const { return _action; }
    QAction* joinAction() const { return _joinAction; }

    // CLI program: $VC_SHEET_CHECK, else vc_sheet_check on PATH.
    static QString resolveProgram();

public slots:
    void run();
    // Join spec: $VC_SHEET_CHECK_JOIN, else a file dialog (not with VC_SHEET_CHECK_NO_DIALOGS).
    void runJoin();

signals:
    // Emitted once per run when it ends: ok is false if any step failed.
    void finished(bool ok);

private:
    QString makeOutDir(const QString& name);
    void start(const Invocation& inv, const QString& entryKey);
    void onFinished(int exitCode, int exitStatus);
    void showReport(const Report& report);
    void ensureDock();
    void jumpToItem(QListWidgetItem* item);
    void fail(const QString& message);

    Host _host;
    QAction* _action{nullptr};
    QAction* _joinAction{nullptr};
    QPointer<QProcess> _proc;
    Invocation _inv;
    QString _segmentIdAtStart;
    QString _entryKey;  // project-entry key: the segment id, or joinEntryKey() in join mode
    bool _failed{false};
    Report _report;
    QPointer<QDockWidget> _dock;
    QPointer<QListWidget> _list;
};

}  // namespace sheetcheck
