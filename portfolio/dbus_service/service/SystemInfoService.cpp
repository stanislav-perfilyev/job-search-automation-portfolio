#include "SystemInfoService.h"
#include <QFile>
#include <QTextStream>
#include <QTimer>
#include <QThread>
#include <QRegularExpression>   // was missing — caused compile error on Qt6

#ifdef Q_OS_LINUX
#  include <unistd.h>
#  include <sys/sysinfo.h>
#endif

SystemInfoService::SystemInfoService(QObject* parent)
    : QObject(parent)
{
    auto* timer = new QTimer(this);
    connect(timer, &QTimer::timeout, this, [this]() {
        const auto mem = GetMemoryInfo();
        const QString info = QStringLiteral("used_mb=%1 total_mb=%2")
            .arg(mem.value(QStringLiteral("used_mb")).toInt())
            .arg(mem.value(QStringLiteral("total_mb")).toInt());
        emit StatsUpdated(info);
    });
    timer->start(5000);
}

QString SystemInfoService::GetHostname() const {
#ifdef Q_OS_LINUX
    char buf[256] = {};
    if (gethostname(buf, sizeof(buf)) == 0)
        return QString::fromUtf8(buf);
#endif
    return QStringLiteral("unknown");
}

QVariantMap SystemInfoService::GetMemoryInfo() const {
    QVariantMap info;

#ifdef Q_OS_LINUX
    struct sysinfo si{};
    if (sysinfo(&si) == 0) {
        const qint64 total_mb = static_cast<qint64>(si.totalram)
                                * si.mem_unit / (1024 * 1024);
        const qint64 free_mb  = static_cast<qint64>(si.freeram)
                                * si.mem_unit / (1024 * 1024);
        info[QStringLiteral("total_mb")] = total_mb;
        info[QStringLiteral("free_mb")]  = free_mb;
        info[QStringLiteral("used_mb")]  = total_mb - free_mb;
    }
#else
    info[QStringLiteral("total_mb")] = 8192;
    info[QStringLiteral("free_mb")]  = 4096;
    info[QStringLiteral("used_mb")]  = 4096;
#endif

    return info;
}

int SystemInfoService::GetCpuCount() const {
    return QThread::idealThreadCount();
}

QString SystemInfoService::GetUptime() const {
#ifdef Q_OS_LINUX
    struct sysinfo si{};
    if (sysinfo(&si) != 0) return QStringLiteral("n/a");
    const long secs = si.uptime;
    const int  h = static_cast<int>(secs / 3600);
    const int  m = static_cast<int>((secs % 3600) / 60);
    return QString::asprintf("%dh %02dm", h, m);
#else
    return QStringLiteral("n/a");
#endif
}

QString SystemInfoService::Echo(const QString& message) const {
    return QStringLiteral("[SystemInfoService] ") + message;
}
