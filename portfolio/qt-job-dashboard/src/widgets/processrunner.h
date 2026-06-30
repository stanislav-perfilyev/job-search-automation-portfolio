#pragma once
#include <QWidget>
#include <QProcess>

class QTextEdit;
class QPushButton;
class QLabel;
class QTimer;

// Runs an external process and streams stdout/stderr into a console widget.
// Features: configurable timeout, console line limit, error signal.
class ProcessRunner final : public QWidget {
    Q_OBJECT
    Q_DISABLE_COPY_MOVE(ProcessRunner)
public:
    static constexpr int kDefaultTimeoutMs  = 5 * 60 * 1000;  // 5 min
    static constexpr int kMaxConsoleBlocks  = 2000;            // lines

    explicit ProcessRunner(QWidget* parent = nullptr);

    void start(const QString& program, const QStringList& args,
               const QString& workingDir = {},
               int timeoutMs = kDefaultTimeoutMs);
    void clear();
    [[nodiscard]] bool isRunning() const noexcept;

signals:
    void finished(int exitCode, QProcess::ExitStatus status);
    void processError(const QString& message);   // ← new error signal

private slots:
    void onReadyStdOut();
    void onReadyStdErr();
    void onFinished(int code, QProcess::ExitStatus status);
    void onKill();
    void onTimeout();

private:
    void appendLine(const QString& text, const QString& color);

    QProcess*    m_proc;
    QTextEdit*   m_console;
    QPushButton* m_killBtn;
    QLabel*      m_statusLabel;
    QTimer*      m_timeoutTimer;
};
