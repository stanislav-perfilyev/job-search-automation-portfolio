#pragma once
#include <QObject>
#include <QTimer>
#include <QString>

// SystemStats exposes CPU load, memory usage and uptime to QML via Q_PROPERTY.
// Backend refreshes every second via QTimer, emitting change signals.

class SystemStats : public QObject {
    Q_OBJECT

    Q_PROPERTY(int    cpuPercent   READ cpuPercent   NOTIFY cpuPercentChanged)
    Q_PROPERTY(int    memPercent   READ memPercent   NOTIFY memPercentChanged)
    Q_PROPERTY(qint64 memUsedMB   READ memUsedMB    NOTIFY memUsedMBChanged)
    Q_PROPERTY(qint64 memTotalMB  READ memTotalMB   NOTIFY memTotalMBChanged)
    Q_PROPERTY(QString uptimeStr  READ uptimeStr    NOTIFY uptimeStrChanged)

public:
    explicit SystemStats(QObject* parent = nullptr);

    int     cpuPercent()  const { return m_cpuPercent;  }
    int     memPercent()  const { return m_memPercent;  }
    qint64  memUsedMB()   const { return m_memUsedMB;   }
    qint64  memTotalMB()  const { return m_memTotalMB;  }
    QString uptimeStr()   const { return m_uptimeStr;   }

signals:
    void cpuPercentChanged();
    void memPercentChanged();
    void memUsedMBChanged();
    void memTotalMBChanged();
    void uptimeStrChanged();

private slots:
    void refresh();

private:
    void updateMemory();
    void updateCpu();
    void updateUptime();

    QTimer  m_timer;
    int     m_cpuPercent  = 0;
    int     m_memPercent  = 0;
    qint64  m_memUsedMB   = 0;
    qint64  m_memTotalMB  = 0;
    QString m_uptimeStr;

    // For delta CPU calculation (Linux /proc/stat)
    qint64  m_prevIdle    = 0;
    qint64  m_prevTotal   = 0;
};
