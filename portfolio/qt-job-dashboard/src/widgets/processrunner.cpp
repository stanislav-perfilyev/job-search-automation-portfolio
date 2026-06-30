#include "processrunner.h"
#include "utils/logging.h"
#include <QTextEdit>
#include <QPushButton>
#include <QLabel>
#include <QTimer>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QScrollBar>
#include <QDateTime>
#include <QFont>

ProcessRunner::ProcessRunner(QWidget* parent)
    : QWidget(parent)
{
    m_proc = new QProcess(this);
    m_proc->setProcessChannelMode(QProcess::SeparateChannels);

    m_console = new QTextEdit(this);
    m_console->setReadOnly(true);
    m_console->setFont(QFont("Courier New", 10));
    m_console->document()->setMaximumBlockCount(kMaxConsoleBlocks);
    m_console->setStyleSheet(
        "background:#0D0D0D; color:#C0C0C0; border:1px solid #2A2A5A;");

    m_killBtn = new QPushButton("✕ Остановить", this);
    m_killBtn->setEnabled(false);
    m_killBtn->setStyleSheet("background:#5C1A1A; color:#E0E0E0;");

    m_statusLabel = new QLabel("Готово", this);
    m_statusLabel->setStyleSheet("color:#8888AA; font-size:11px;");

    m_timeoutTimer = new QTimer(this);
    m_timeoutTimer->setSingleShot(true);

    auto* bar = new QHBoxLayout;
    bar->addWidget(m_statusLabel);
    bar->addStretch();
    bar->addWidget(m_killBtn);

    auto* root = new QVBoxLayout(this);
    root->addWidget(m_console);
    root->addLayout(bar);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(4);

    connect(m_proc, &QProcess::readyReadStandardOutput, this, &ProcessRunner::onReadyStdOut);
    connect(m_proc, &QProcess::readyReadStandardError,  this, &ProcessRunner::onReadyStdErr);
    connect(m_proc, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            this, &ProcessRunner::onFinished);
    connect(m_killBtn,      &QPushButton::clicked, this, &ProcessRunner::onKill);
    connect(m_timeoutTimer, &QTimer::timeout,      this, &ProcessRunner::onTimeout);
}

void ProcessRunner::start(const QString& program, const QStringList& args,
                          const QString& workingDir, int timeoutMs)
{
    if (m_proc->state() != QProcess::NotRunning) {
        qCWarning(lcProc) << "start() called while already running";
        return;
    }

    if (!workingDir.isEmpty())
        m_proc->setWorkingDirectory(workingDir);

    const QString ts = QDateTime::currentDateTime().toString("HH:mm:ss");
    appendLine(QString("▶ [%1] %2 %3").arg(ts, program, args.join(' ')), "#4A9EFF");
    qCDebug(lcProc) << "Starting" << program << args << "in" << workingDir;

    m_proc->start(program, args);
    if (!m_proc->waitForStarted(3000)) {
        const QString msg = "Failed to start: " + m_proc->errorString();
        appendLine("✗ " + msg, "#FF5555");
        qCWarning(lcProc) << msg;
        emit processError(msg);
        return;
    }

    m_killBtn->setEnabled(true);
    m_statusLabel->setText("⏳ Выполняется…");

    if (timeoutMs > 0)
        m_timeoutTimer->start(timeoutMs);
}

bool ProcessRunner::isRunning() const noexcept
{
    return m_proc->state() != QProcess::NotRunning;
}

void ProcessRunner::clear()
{
    m_console->clear();
}

void ProcessRunner::onReadyStdOut()
{
    const QString text = QString::fromUtf8(m_proc->readAllStandardOutput());
    for (const auto& line : text.split('\n'))
        if (!line.trimmed().isEmpty())
            appendLine(line, "#C0C0C0");
}

void ProcessRunner::onReadyStdErr()
{
    const QString text = QString::fromUtf8(m_proc->readAllStandardError());
    for (const auto& line : text.split('\n'))
        if (!line.trimmed().isEmpty())
            appendLine(line, "#FF9955");
}

void ProcessRunner::onFinished(int code, QProcess::ExitStatus status)
{
    m_timeoutTimer->stop();
    onReadyStdOut();   // drain remaining output
    onReadyStdErr();

    m_killBtn->setEnabled(false);
    const bool ok = (status == QProcess::NormalExit && code == 0);
    appendLine(ok ? "✓ Завершено (код 0)"
                  : QString("✗ Завершено с кодом %1").arg(code),
               ok ? "#2ECC71" : "#FF5555");
    m_statusLabel->setText(ok ? "✓ Успешно" : QString("✗ Код %1").arg(code));

    qCInfo(lcProc) << "Process finished, exit code" << code
                   << (ok ? "(OK)" : "(FAIL)");
    emit finished(code, status);
}

void ProcessRunner::onKill()
{
    m_timeoutTimer->stop();
    if (m_proc->state() != QProcess::NotRunning) {
        m_proc->kill();
        appendLine("⚠ Процесс остановлен пользователем", "#F39C12");
        qCWarning(lcProc) << "Process killed by user";
    }
}

void ProcessRunner::onTimeout()
{
    if (m_proc->state() != QProcess::NotRunning) {
        m_proc->kill();
        const QString msg = "Process timed out and was killed";
        appendLine("⚠ Таймаут — процесс принудительно остановлен", "#F39C12");
        qCWarning(lcProc) << msg;
        emit processError(msg);
    }
}

void ProcessRunner::appendLine(const QString& text, const QString& color)
{
    m_console->append(QString("<span style='color:%1;'>%2</span>")
        .arg(color, text.toHtmlEscaped()));
    auto* sb = m_console->verticalScrollBar();
    sb->setValue(sb->maximum());
}
