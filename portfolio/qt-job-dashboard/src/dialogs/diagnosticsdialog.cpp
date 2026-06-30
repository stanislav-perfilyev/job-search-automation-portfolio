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

DiagnosticsDialog::DiagnosticsDialog(IVacancyModel* model, QWidget* parent)
    : QDialog(parent), m_model(model)
{
    setWindowTitle("Диагностика системы");
    setMinimumSize(600, 420);

    m_output     = new QTextEdit(this);
    m_output->setReadOnly(true);
    m_output->setFont(QFont("Courier New", 10));
    m_output->setStyleSheet("background:#0D0D0D; color:#C0C0C0;");

    m_refreshBtn = new QPushButton("⟳ Повторить", this);
    auto* closeBtn = new QDialogButtonBox(QDialogButtonBox::Close, this);

    auto* bar = new QHBoxLayout;
    bar->addWidget(m_refreshBtn);
    bar->addStretch();
    bar->addWidget(closeBtn);

    auto* root = new QVBoxLayout(this);
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
    QVector<Check> checks;

    // 1. DB driver available
    {
        const bool ok = QSqlDatabase::isDriverAvailable("QPSQL");
        checks.push_back({"Qt QPSQL driver", ok,
            ok ? "доступен" : "QPSQL драйвер не установлен (libqt6sql-psql)"});
    }

    // 2. DB connection open
    {
        const QSqlDatabase db = QSqlDatabase::database("dashboard_main");
        const bool ok = db.isOpen();
        checks.push_back({"DB connection open", ok,
            ok ? db.hostName() + "/" + db.databaseName()
               : "Нет подключения — откройте Файл → Настройки"});
    }

    // 3. DB ping
    {
        const QSqlDatabase db = QSqlDatabase::database("dashboard_main");
        bool ok = false; QString detail;
        if (db.isOpen()) {
            QSqlQuery q(db);
            ok = q.exec("SELECT NOW()::text");
            detail = ok ? q.first() ? q.value(0).toString() : "OK"
                        : q.lastError().text();
        } else {
            detail = "пропущено (нет соединения)";
        }
        checks.push_back({"DB ping (SELECT NOW())", ok, detail});
    }

    // 4. Model loaded
    {
        const int n = m_model->totalCount();
        const bool ok = n > 0;
        checks.push_back({"Model data loaded", ok,
            ok ? QString("%1 вакансий в памяти").arg(n)
               : "0 вакансий — не загружены или БД пуста"});
    }

    // 5. Model healthCheck
    {
        const QString hc = m_model->healthCheck();
        const bool ok = hc.isEmpty();
        checks.push_back({"Model healthCheck()", ok,
            ok ? "OK" : hc});
    }

    // 6. Free disk space
    {
        const QStorageInfo storage = QStorageInfo::root();
        const qint64 freeMb = storage.bytesFree() / 1024 / 1024;
        const bool ok = freeMb > 100;
        checks.push_back({"Disk space (root)", ok,
            QString("%1 MB свободно%2").arg(freeMb).arg(ok ? "" : " ⚠ мало места")});
    }

    // 7. Qt version
    {
        checks.push_back({"Qt version", true,
            QString(QT_VERSION_STR) + " (min: 6.0)"});
    }

    return checks;
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
