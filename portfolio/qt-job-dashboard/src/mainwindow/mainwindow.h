#pragma once
#include <QMainWindow>

class VacancySqlModel;
class VacancyView;
class StatisticsView;
class KpiWidget;
class QTabWidget;
class QLabel;
class QTimer;

class MainWindow final : public QMainWindow {
    Q_OBJECT
    Q_DISABLE_COPY_MOVE(MainWindow)
public:
    explicit MainWindow(QWidget* parent = nullptr);
    ~MainWindow() override;

private slots:
    void onRefresh();
    void onVacancyDoubleClicked(int row);
    void onSettings();
    void onExportCsv();
    void onRunScript();
    void onDiagnostics();
    void onAbout();
    void updateKpis();

private:
    [[nodiscard]] bool    connectDb();
    void    setupUi();
    void    applyDarkTheme();
    void    createStatusBar();
    [[nodiscard]] QString projectRoot() const;

    VacancySqlModel* m_model{};
    VacancyView*     m_vacancyView{};
    StatisticsView*  m_statsView{};
    QTabWidget*      m_tabs{};
    QLabel*          m_statusLabel{};
    QTimer*          m_autoRefresh{};
    KpiWidget*       m_kpiTotal{};
    KpiWidget*       m_kpiActive{};
    KpiWidget*       m_kpiInterview{};
    KpiWidget*       m_kpiConversion{};
};
