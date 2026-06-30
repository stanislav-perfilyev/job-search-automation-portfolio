#include <QtTest/QtTest>
#include "../service/SystemInfoService.h"

// Tests the SERVICE LOGIC without real D-Bus:
//   - Correct types returned
//   - Echo round-trips
//   - Memory info is consistent
//   - CPU count is positive

class TestSystemInfoService : public QObject {
    Q_OBJECT

private:
    SystemInfoService m_service;

private slots:
    void test_echo_roundtrip() {
        const QString msg    = QStringLiteral("hello world");
        const QString result = m_service.Echo(msg);
        QVERIFY2(result.contains(msg),
                 "Echo must contain the original message");
        QVERIFY2(result.startsWith(QStringLiteral("[SystemInfoService]")),
                 "Echo must be prefixed with service stamp");
    }

    void test_hostname_notEmpty() {
        QVERIFY2(!m_service.GetHostname().isEmpty(),
                 "Hostname must not be empty");
    }

    void test_cpuCount_positive() {
        QVERIFY2(m_service.GetCpuCount() > 0,
                 "CPU count must be > 0");
    }

    void test_memoryInfo_hasRequiredKeys() {
        const QVariantMap mem = m_service.GetMemoryInfo();
        QVERIFY2(mem.contains(QStringLiteral("total_mb")), "Must have total_mb");
        QVERIFY2(mem.contains(QStringLiteral("free_mb")),  "Must have free_mb");
        QVERIFY2(mem.contains(QStringLiteral("used_mb")),  "Must have used_mb");
    }

    void test_memoryInfo_valuesNonNegative() {
        const QVariantMap mem = m_service.GetMemoryInfo();
        QVERIFY2(mem[QStringLiteral("total_mb")].toLongLong() >= 0, "total_mb >= 0");
        QVERIFY2(mem[QStringLiteral("free_mb")].toLongLong()  >= 0, "free_mb >= 0");
        QVERIFY2(mem[QStringLiteral("used_mb")].toLongLong()  >= 0, "used_mb >= 0");
    }

    void test_memoryInfo_usedPlusFreeLeTotal() {
        const QVariantMap mem   = m_service.GetMemoryInfo();
        const qint64 total = mem[QStringLiteral("total_mb")].toLongLong();
        const qint64 free_ = mem[QStringLiteral("free_mb")].toLongLong();
        const qint64 used  = mem[QStringLiteral("used_mb")].toLongLong();
        QVERIFY2(used + free_ <= total + 1, // +1 for rounding tolerance
                 "used + free must not exceed total");
    }

    void test_uptime_notEmpty() {
        QVERIFY2(!m_service.GetUptime().isEmpty(),
                 "Uptime must not be empty");
    }

    void test_statsUpdated_signalEmitted() {
        QSignalSpy spy(&m_service, &SystemInfoService::StatsUpdated);
        // Signal fires every 5s — wait long enough
        QVERIFY2(spy.wait(6000), "StatsUpdated signal should fire within 6 seconds");
        QVERIFY2(!spy.isEmpty(), "Signal should have been emitted");
        const QString payload = spy.first().first().toString();
        QVERIFY2(payload.contains(QStringLiteral("used_mb")),
                 "Signal payload must contain used_mb");
    }
};

QTEST_MAIN(TestSystemInfoService)
#include "test_dbus_service.moc"
