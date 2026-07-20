#include "mainwindow.h"
#include "models/vacancysqlmodel.h"
#include "views/vacancyview.h"
#include "views/statisticsview.h"
#include "widgets/kpiwidget.h"
#include "dialogs/vacancydetaildialog.h"
#include "dialogs/settingsdialog.h"
#include "dialogs/scriptdialog.h"
#include "dialogs/diagnosticsdialog.h"
#include "utils/csvexporter.h"
#include "utils/status.h"
#include "utils/logging.h"
#include <QTabWidget>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QTimer>
#include <QTime>
#include <QMenuBar>
#include <QStatusBar>
#include <QSettings>
#include <QApplication>
#include <QMessageBox>
#include <QFile>
#include <QDir>

namespace {
    constexpr int kProjectRootSearchDepth = 6;   // was magic 8
    constexpr int kAutoRefreshIntervalMs  = 5 * 60 * 1000;
} // anonymous namespace

MainWindow::MainWindow(QWidget* parent)
    : QMainWindow(parent)
{
    setWindowTitle("Job Search Dashboard");
    resize(1400, 800);

    applyDarkTheme();

    m_model = new VacancySqlModel(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented

    setupUi();
    createStatusBar();

    // Wire model error signal → status bar (non-critical) and log
    connect(m_model, &IVacancyModel::error, this, [this](const QString& msg){
        m_statusLabel->setText("⚠ " + msg);
        qCWarning(lcUi) << "Model error:" << msg;
    });

    if (!connectDb()) {
        m_statusLabel->setText("⚠ БД не подключена — Файл → Настройки");
    } else {
        if (m_model->refresh())
            updateKpis();
    }

    m_autoRefresh = new QTimer(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    m_autoRefresh->setInterval(kAutoRefreshIntervalMs);
    connect(m_autoRefresh, &QTimer::timeout, this, &MainWindow::onRefresh);
    m_autoRefresh->start();
}

MainWindow::~MainWindow() = default;

bool MainWindow::connectDb()
{
    QSettings s("JobDashboard", "db");
    const QString host = s.value("host").toString();
    if (host.isEmpty()) return false;

    return VacancySqlModel::connectDatabase(
        host,
        s.value("database").toString(),
        s.value("user").toString(),
        s.value("password").toString(),
        s.value("port", 5432).toInt()
    );
}

QString MainWindow::projectRoot() const
{
    QSettings s("JobDashboard", "scripts");
    const QString saved = s.value("projectRoot").toString();
    if (!saved.isEmpty() && QDir(saved).exists()) return saved;

    QDir d = QDir::current();
    for (int i = 0; i < kProjectRootSearchDepth; ++i) {
        if (QFile::exists(d.filePath("add_vacancy.py")))
            return d.absolutePath();
        if (!d.cdUp()) break;
    }
    return QDir::homePath();
}

void MainWindow::setupUi()
{
    m_kpiTotal      = new KpiWidget("Всего откликов", "#4A9EFF", this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    m_kpiActive     = new KpiWidget("Активных",       "#2ECC71", this);  // NOLINT(cppcoreguidelines-owning-memory)
    m_kpiInterview  = new KpiWidget("Интервью",       "#F39C12", this);  // NOLINT(cppcoreguidelines-owning-memory)
    m_kpiConversion = new KpiWidget("Конверсия %",    "#9B59B6", this);  // NOLINT(cppcoreguidelines-owning-memory)

    auto* kpiRow = new QHBoxLayout;  // NOLINT(cppcoreguidelines-owning-memory) — reparented by addLayout below
    for (auto* w : {m_kpiTotal, m_kpiActive, m_kpiInterview, m_kpiConversion})
        kpiRow->addWidget(w);

    m_vacancyView = new VacancyView(m_model, this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    m_statsView   = new StatisticsView(m_model, this);  // NOLINT(cppcoreguidelines-owning-memory)

    m_tabs = new QTabWidget(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    m_tabs->addTab(m_vacancyView, "📋 Вакансии");
    m_tabs->addTab(m_statsView,  "📊 Статистика");

    auto* root = new QVBoxLayout;  // NOLINT(cppcoreguidelines-owning-memory) — reparented by setLayout below
    root->addLayout(kpiRow);
    root->addWidget(m_tabs);
    root->setSpacing(8);
    root->setContentsMargins(8, 8, 8, 8);

    auto* central = new QWidget(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    central->setLayout(root);
    setCentralWidget(central);

    // ── Меню ──────────────────────────────────────────────────
    auto* fileMenu = menuBar()->addMenu("&Файл");
    fileMenu->addAction("⚙ Настройки", this, &MainWindow::onSettings);
    fileMenu->addSeparator();
    fileMenu->addAction("📄 Экспорт в CSV", QKeySequence("Ctrl+E"),
                        this, &MainWindow::onExportCsv);
    fileMenu->addSeparator();
    fileMenu->addAction("Выход", QKeySequence::Quit, qApp, &QApplication::quit);

    auto* viewMenu = menuBar()->addMenu("&Вид");
    viewMenu->addAction("⟳ Обновить", QKeySequence::Refresh,
                        this, &MainWindow::onRefresh);

    auto* toolsMenu = menuBar()->addMenu("&Инструменты");
    toolsMenu->addAction("🐍 Запустить Python скрипт…", QKeySequence("Ctrl+R"),
                         this, &MainWindow::onRunScript);

    auto* helpMenu = menuBar()->addMenu("&Справка");
    helpMenu->addAction("🔍 Диагностика", this, &MainWindow::onDiagnostics);
    helpMenu->addSeparator();
    helpMenu->addAction("О программе", this, &MainWindow::onAbout);

    connect(m_vacancyView, &VacancyView::refreshRequested,     this, &MainWindow::onRefresh);
    connect(m_vacancyView, &VacancyView::vacancyDoubleClicked, this, &MainWindow::onVacancyDoubleClicked);
}

void MainWindow::createStatusBar()
{
    m_statusLabel = new QLabel("Готово", this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    statusBar()->addPermanentWidget(m_statusLabel);
}

void MainWindow::onRefresh()
{
    if (m_model->refresh()) {
        m_statsView->refresh();
        updateKpis();
        m_statusLabel->setText(QString("Обновлено: %1")
            .arg(QTime::currentTime().toString("HH:mm:ss")));
    }
}

void MainWindow::onVacancyDoubleClicked(int row)
{
    VacancyDetailDialog dlg(m_model, row, this);
    dlg.exec();
}

void MainWindow::onSettings()
{
    SettingsDialog dlg(this);
    if (dlg.exec() == QDialog::Accepted) {
        const auto cfg = dlg.config();
        if (VacancySqlModel::connectDatabase(
                cfg.host, cfg.database, cfg.user, cfg.password, cfg.port)) {
            if (m_model->refresh()) updateKpis();
            m_statusLabel->setText("БД подключена ✓");
        } else {
            m_statusLabel->setText("⚠ Ошибка подключения");
        }
    }
}

void MainWindow::onExportCsv()
{
    if (CsvExporter::exportModel(m_model, {}, this))
        m_statusLabel->setText("CSV экспортирован ✓");
}

void MainWindow::onRunScript()
{
    ScriptDialog dlg(projectRoot(), this);
    dlg.exec();
}

void MainWindow::onDiagnostics()
{
    DiagnosticsDialog dlg(m_model, this);
    dlg.exec();
}

void MainWindow::onAbout()
{
    QMessageBox::about(this, "О программе",
        "<b>Job Search Dashboard</b> v1.2<br>"
        "Qt6 C++17 · PostgreSQL/Neon<br>"
        "Senior review: error signals, diagnostics, RAII, logging<br>"
        "Portfolio project #8 — Stanislav Perfiliev");
}

void MainWindow::updateKpis()
{
    const int total     = m_model->totalCount();
    const int active    = m_model->countByStatus(Status::Applied)
                        + m_model->countByStatus(Status::Viewed);
    const int interview = m_model->countByStatus(Status::Interview);
    const int offer     = m_model->countByStatus(Status::Offer);
    const int conv      = total > 0 ? (interview + offer) * 100 / total : 0;

    m_kpiTotal->setValue(total);
    m_kpiActive->setValue(active);
    m_kpiInterview->setValue(interview);
    m_kpiConversion->setValue(conv);
    m_kpiConversion->setSubtitle(QString("%1 оффер(ов)").arg(offer));
}

void MainWindow::applyDarkTheme()
{
    QFile f(":/style.qss");
    if (f.open(QFile::ReadOnly))
        qApp->setStyleSheet(QString::fromUtf8(f.readAll()));
}
