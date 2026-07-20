#include "diagnosticsdialog.h"
#include "models/ivacancymodel.h"
#include <QTextEdit>
#include <QPushButton>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QDialogButtonBox>
#include <QSqlDatabase>
#include <QSqlQuery>
#include <QSqlError>
#include <QDateTime>
#include <QStorageInfo>

namespace {
constexpr int kDialogWidth       = 600;
constexpr int kDialogHeight      = 420;
constexpr int kMonospaceFontSize = 10;
constexpr qint64 kBytesPerMiB    = 1024 * 1024;
constexpr qint64 kMinFreeSpaceMb = 100;
}  // namespace

DiagnosticsDialog::DiagnosticsDialog(IVacancyModel* model, QWidget* parent)
    : QDialog(parent), m_model(model)
{
    setWindowTitle("Диагностика системы");
    setMinimumSize(kDialogWidth, kDialogHeight);

    m_output = new QTextEdit(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    m_output->setReadOnly(true);
    m_output->setFont(QFont("Courier New", kMonospaceFontSize));
    m_output->setStyleSheet("background:#0D0D0D; color:#C0C0C0;");

    m_refreshBtn = new QPushButton("⟳ Повторить", this);  // NOLINT(cppcoreguidelines-owning-memory)
    auto* closeBtn = new QDialogButtonBox(QDialogButtonBox::Close, this);  // NOLINT(cppcoreguidelines-owning-memory)

    auto* bar = new QHBoxLayout;  // NOLINT(cppcoreguidelines-owning-memory) — reparented by addLayout below
    bar->addWidget(m_refreshBtn);
    bar->addStretch();
    bar->addWidget(closeBtn);

    auto* root = new QVBoxLayout(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    root->addWidget(m_output);
    root->addLayout(bar);

    connect(m_refreshBtn, &QPushButton::clicked, this, &DiagnosticsDialog::runDiagnostics);
    connect(closeBtn, &QDialogButtonBox::rejected, this, &QDialog::reject);

    runDiagnostics();
}

void DiagnosticsDialog::runDiagnostics()
{
    m_output->clear();
    renderReport(collectChecks());
}

QVector<DiagnosticsDialog::Check> DiagnosticsDialog::collectChecks() const
{
    return {
        checkDriverAvailable(),
        checkConnectionOpen(),
        checkDbPing(),
        checkModelLoaded(),
        checkModelHealth(),
        checkDiskSpace(),
        checkQtVersion(),
    };
}

DiagnosticsDialog::Check DiagnosticsDialog::checkDriverAvailable() const
{
    const bool ok = QSqlDatabase::isDriverAvailable("QPSQL");
    return {"Qt QPSQL driver", ok,
        ok ? "доступен" : "QPSQL драйвер не установлен (libqt6sql-psql)"};
}

DiagnosticsDialog::Check DiagnosticsDialog::checkConnectionOpen() const
{
    const QSqlDatabase db = QSqlDatabase::database("dashboard_main");
    const bool ok = db.isOpen();
    return {"DB connection open", ok,
        ok ? db.hostName() + "/" + db.databaseName()
           : "Нет подключения — откройте Файл → Настройки"};
}

DiagnosticsDialog::Check DiagnosticsDialog::checkDbPing() const
{
    const QSqlDatabase db = QSqlDatabase::database("dashboard_main");
    bool ok = false;
    QString detail;
    if (db.isOpen()) {
        QSqlQuery q(db);
        ok = q.exec("SELECT NOW()::text");
        detail = ok ? q.first() ? q.value(0).toString() : "OK"
                    : q.lastError().text();
    } else {
        detail = "пропущено (нет соединения)";
    }
    return {"DB ping (SELECT NOW())", ok, detail};
}

DiagnosticsDialog::Check DiagnosticsDialog::checkModelLoaded() const
{
    const int n = m_model->totalCount();
    const bool ok = n > 0;
    return {"Model data loaded", ok,
        ok ? QString("%1 вакансий в памяти").arg(n)
           : "0 вакансий — не загружены или БД пуста"};
}

DiagnosticsDialog::Check DiagnosticsDialog::checkModelHealth() const
{
    const QString hc = m_model->healthCheck();
    const bool ok = hc.isEmpty();
    return {"Model healthCheck()", ok, ok ? "OK" : hc};
}

DiagnosticsDialog::Check DiagnosticsDialog::checkDiskSpace() const
{
    const QStorageInfo storage = QStorageInfo::root();
    const qint64 freeMb = storage.bytesFree() / kBytesPerMiB;
    const bool ok = freeMb > kMinFreeSpaceMb;
    return {"Disk space (root)", ok,
        QString("%1 MB свободно%2").arg(freeMb).arg(ok ? "" : " ⚠ мало места")};
}

DiagnosticsDialog::Check DiagnosticsDialog::checkQtVersion() const
{
    return {"Qt version", true, QString(QT_VERSION_STR) + " (min: 6.0)"};
}

void DiagnosticsDialog::renderReport(const QVector<Check>& checks)
{
    QString html;
    html += QString("<b>Диагностика: %1</b><br><br>")
                .arg(QDateTime::currentDateTime().toString("dd.MM.yyyy HH:mm:ss"));

    int passed = 0, failed = 0;
    for (const auto& c : checks) {
        const QString icon   = c.passed ? "✓" : "✗";
        const QString colour = c.passed ? "#2ECC71" : "#FF5555";
        html += QString("<span style='color:%1;'>%2 <b>%3</b></span> — %4<br>")
                    .arg(colour, icon, c.name.toHtmlEscaped(), c.detail.toHtmlEscaped());
        c.passed ? ++passed : ++failed;
    }

    html += QString("<br><b>Итог: %1 OK / %2 FAIL</b>").arg(passed).arg(failed);
    m_output->setHtml(html);
}
