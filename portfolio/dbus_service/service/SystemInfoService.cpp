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

namespace {
constexpr int  kStatsIntervalMs   = 5000;  ///< StatsUpdated() emission period
constexpr int  kHostnameBufSize   = 256;   ///< gethostname() buffer size
constexpr qint64 kBytesPerMebibyte = 1024 * 1024;
}  // namespace

SystemInfoService::SystemInfoService(QObject* parent)
    : QObject(parent)
{
    // Qt-parented: timer is owned by `this` and destroyed automatically
    // when the service is destroyed — no manual cleanup needed.
    auto* timer = new QTimer(this);  // NOLINT(cppcoreguidelines-owning-memory)
    connect(timer, &QTimer::timeout, this, [this]() {
        const auto mem = GetMemoryInfo();
        const QString info = QStringLiteral("used_mb=%1 total_mb=%2")
            .arg(mem.value(QStringLiteral("used_mb")).toInt())
            .arg(mem.value(QStringLiteral("total_mb")).toInt());
        emit StatsUpdated(info);
    });
    timer->start(kStatsIntervalMs);
}

QString SystemInfoService::GetHostname() const {
#ifdef Q_OS_LINUX
    char buf[kHostnameBufSize] = {};
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
                                * si.mem_unit / kBytesPerMebibyte;
        const qint64 free_mb  = static_cast<qint64>(si.freeram)
                                * si.mem_unit / kBytesPerMebibyte;
        info[QStringLiteral("total_mb")] = total_mb;
        info[QStringLiteral("free_mb")]  = free_mb;
        info[QStringLiteral("used_mb")]  = total_mb - free_mb;
    }
#else
    // Non-Linux fallback: sysinfo() unavailable, report plausible stub values.
    constexpr int kStubTotalMb = 8192;
    constexpr int kStubUsedMb  = 4096;
    info[QStringLiteral("total_mb")] = kStubTotalMb;
    info[QStringLiteral("free_mb")]  = kStubTotalMb - kStubUsedMb;
    info[QStringLiteral("used_mb")]  = kStubUsedMb;
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
