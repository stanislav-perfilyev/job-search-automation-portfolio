#include "SystemStats.h"
#include <QFile>
#include <QTextStream>
#include <QRegularExpression>

#ifdef Q_OS_WIN
#  include <windows.h>
#  include <psapi.h>
#endif

namespace {
constexpr int    kRefreshIntervalMs = 1000;
constexpr qint64 kKiBPerMiB         = 1024;
constexpr qint64 kBytesPerMiB       = 1024 * 1024;
constexpr int    kPercentScale      = 100;
constexpr int    kSecondsPerHour    = 3600;
constexpr int    kSecondsPerMinute  = 60;
constexpr qint64 kStubTotalMb       = 8192;
constexpr qint64 kStubUsedMb        = 4096;
}  // namespace

SystemStats::SystemStats(QObject* parent)
    : QObject(parent)
{
    connect(&m_timer, &QTimer::timeout, this, &SystemStats::refresh);
    m_timer.start(kRefreshIntervalMs);
    refresh(); // populate immediately on creation
}

void SystemStats::refresh() {
    updateMemory();
    updateCpu();
    updateUptime();
}

void SystemStats::updateMemory() {
    qint64 usedMB  = 0;
    qint64 totalMB = 0;

#ifdef Q_OS_LINUX
    QFile f(QStringLiteral("/proc/meminfo"));
    if (!f.open(QIODevice::ReadOnly)) return;

    QTextStream ts(&f);
    static const QRegularExpression re(QStringLiteral("^(\\w+):\\s+(\\d+)"));

    qint64 free_kB      = 0;
    qint64 available_kB = 0;
    qint64 total_kB     = 0;

    QString line;
    while (ts.readLineInto(&line)) {
        const auto m = re.match(line);
        if (!m.hasMatch()) continue;
        const QString key = m.captured(1);
        const qint64  val = m.captured(2).toLongLong();

        if      (key == QLatin1String("MemTotal"))     total_kB     = val;
        else if (key == QLatin1String("MemFree"))      free_kB      = val;
        else if (key == QLatin1String("MemAvailable")) available_kB = val;
    }

    totalMB = total_kB     / kKiBPerMiB;
    usedMB  = (total_kB - available_kB) / kKiBPerMiB;

#elif defined(Q_OS_WIN)
    MEMORYSTATUSEX ms{};
    ms.dwLength = sizeof(ms);
    if (GlobalMemoryStatusEx(&ms)) {
        totalMB = static_cast<qint64>(ms.ullTotalPhys)    / kBytesPerMiB;
        usedMB  = static_cast<qint64>(ms.ullTotalPhys
                                    - ms.ullAvailPhys)    / kBytesPerMiB;
    }
#else
    totalMB = kStubTotalMb;
    usedMB  = kStubUsedMb;
#endif

    const int pct = (totalMB > 0)
        ? static_cast<int>(usedMB * kPercentScale / totalMB)
        : 0;

    // Emit only on actual change — avoid spurious QML updates
    if (m_memTotalMB != totalMB) { m_memTotalMB = totalMB; emit memTotalMBChanged(); }
    if (m_memUsedMB  != usedMB)  { m_memUsedMB  = usedMB;  emit memUsedMBChanged();  }
    if (m_memPercent != pct)     { m_memPercent  = pct;     emit memPercentChanged(); }
}

void SystemStats::updateCpu() {
    int pct = 0;

#ifdef Q_OS_LINUX
    QFile f(QStringLiteral("/proc/stat"));
    if (!f.open(QIODevice::ReadOnly)) return;

    const QString line = QString::fromLatin1(f.readLine());
    const QStringList parts = line.split(QLatin1Char(' '), Qt::SkipEmptyParts);
    // Format: cpu user nice system idle iowait irq softirq steal …
    if (parts.size() < 5 || parts.first() != QLatin1String("cpu")) return;

    const qint64 user    = parts[1].toLongLong();
    const qint64 nice    = parts[2].toLongLong();
    const qint64 system  = parts[3].toLongLong();
    const qint64 idle    = parts[4].toLongLong();
    const qint64 iowait  = parts.size() > 5 ? parts[5].toLongLong() : 0;
    const qint64 irq     = parts.size() > 6 ? parts[6].toLongLong() : 0;
    const qint64 softirq = parts.size() > 7 ? parts[7].toLongLong() : 0;

    const qint64 totalIdle = idle + iowait;
    const qint64 total     = user + nice + system + totalIdle + irq + softirq;

    const qint64 dTotal = total - m_prevTotal;
    const qint64 dIdle  = totalIdle - m_prevIdle;

    m_prevTotal = total;
    m_prevIdle  = totalIdle;

    if (dTotal > 0)
        pct = static_cast<int>((dTotal - dIdle) * kPercentScale / dTotal);

#elif defined(Q_OS_WIN)
    static FILETIME sPrevIdle{}, sPrevKernel{}, sPrevUser{};
    FILETIME idle{}, kernel{}, user{};
    if (!GetSystemTimes(&idle, &kernel, &user)) return;

    auto toU64 = [](FILETIME ft) -> ULONGLONG {
        return (ULONGLONG(ft.dwHighDateTime) << 32) | ft.dwLowDateTime;
    };
    const ULONGLONG dIdle   = toU64(idle)   - toU64(sPrevIdle);
    const ULONGLONG dKernel = toU64(kernel) - toU64(sPrevKernel);
    const ULONGLONG dUser   = toU64(user)   - toU64(sPrevUser);
    sPrevIdle = idle; sPrevKernel = kernel; sPrevUser = user;

    const ULONGLONG total = dKernel + dUser;
    if (total > 0)
        pct = static_cast<int>((total - dIdle) * kPercentScale / total);
#endif

    pct = qBound(0, pct, kPercentScale);
    if (m_cpuPercent != pct) { m_cpuPercent = pct; emit cpuPercentChanged(); }
}

void SystemStats::updateUptime() {
    QString str;

#ifdef Q_OS_LINUX
    QFile f(QStringLiteral("/proc/uptime"));
    if (!f.open(QIODevice::ReadOnly)) return;

    const double secs = f.readLine()
                         .split(QLatin1Char(' '))
                         .first()
                         .toDouble();
    const int h = static_cast<int>(secs) / kSecondsPerHour;
    const int m = (static_cast<int>(secs) % kSecondsPerHour) / kSecondsPerMinute;
    const int s = static_cast<int>(secs) % kSecondsPerMinute;
    str = QString::asprintf("%dh %02dm %02ds", h, m, s);
#else
    str = QStringLiteral("n/a");
#endif

    if (m_uptimeStr != str) { m_uptimeStr = str; emit uptimeStrChanged(); }
}
