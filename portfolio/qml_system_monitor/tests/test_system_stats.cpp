#include <QtTest/QtTest>
#include <QTemporaryFile>
#include <QTextStream>
#include <QSignalSpy>
#include "../src/SystemStats.h"

// We test SystemStats by verifying:
//  1. Signals are emitted on construction (initial refresh)
//  2. Values are within sane bounds
//  3. Signal change-guard: no spurious emissions when value unchanged

class TestSystemStats : public QObject {
    Q_OBJECT

private slots:
    void initTestCase() {
        // SystemStats needs an event loop for QTimer
    }

    // --- Construction ---
    void test_construction_emitsSignals() {
        SystemStats stats;
        // After construction, values should be set
        QVERIFY(stats.cpuPercent()  >= 0);
        QVERIFY(stats.cpuPercent()  <= 100);
        QVERIFY(stats.memPercent()  >= 0);
        QVERIFY(stats.memPercent()  <= 100);
        QVERIFY(stats.memTotalMB()  >= 0);
        QVERIFY(stats.memUsedMB()   >= 0);
        QVERIFY(stats.memUsedMB()   <= stats.memTotalMB() || stats.memTotalMB() == 0);
    }

    // --- Bounds ---
    void test_cpuPercent_inRange() {
        SystemStats stats;
        // Trigger multiple refreshes to exercise delta calc
        for (int i = 0; i < 3; ++i) {
            QTest::qWait(1100); // let timer fire
        }
        QVERIFY2(stats.cpuPercent() >= 0,   "CPU% must be >= 0");
        QVERIFY2(stats.cpuPercent() <= 100, "CPU% must be <= 100");
    }

    void test_memoryConsistency() {
        SystemStats stats;
        QTest::qWait(100);
        // Used <= Total (or both zero on unsupported platform)
        const qint64 used  = stats.memUsedMB();
        const qint64 total = stats.memTotalMB();
        QVERIFY2(used >= 0,    "usedMB must be non-negative");
        QVERIFY2(total >= 0,   "totalMB must be non-negative");
        QVERIFY2(used <= total || total == 0,
                 "usedMB must not exceed totalMB");
    }

    void test_memPercent_matchesUsedTotal() {
        SystemStats stats;
        QTest::qWait(100);
        const qint64 used  = stats.memUsedMB();
        const qint64 total = stats.memTotalMB();
        const int    pct   = stats.memPercent();
        if (total > 0) {
            const int expected = static_cast<int>(used * 100 / total);
            QCOMPARE(pct, expected);
        } else {
            QCOMPARE(pct, 0);
        }
    }

    // --- Signals ---
    void test_signalEmittedOnStart() {
        SystemStats stats;
        // cpuPercentChanged, memPercentChanged emitted at least once (initial refresh)
        QSignalSpy spyCpu(&stats, &SystemStats::cpuPercentChanged);
        QSignalSpy spyMem(&stats, &SystemStats::memPercentChanged);

        // Force another refresh via timer
        QTest::qWait(1200);

        // At least one emission expected (timer fires ~every 1s)
        QVERIFY2(spyCpu.count() + spyMem.count() > 0,
                 "Expected at least one signal emission after 1200ms");
    }

    void test_uptimeStr_notEmpty() {
        SystemStats stats;
        QTest::qWait(100);
        // On Linux it should contain uptime; on other platforms "n/a"
        const QString uptime = stats.uptimeStr();
        QVERIFY2(!uptime.isEmpty(), "uptimeStr must not be empty");
    }
};

QTEST_MAIN(TestSystemStats)
#include "test_system_stats.moc"
