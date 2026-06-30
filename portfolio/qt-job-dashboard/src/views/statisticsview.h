#pragma once
#include <QWidget>

class VacancySqlModel;
class QHBoxLayout;
namespace QtCharts { class QChartView; }

class StatisticsView final : public QWidget {
    Q_OBJECT
    Q_DISABLE_COPY_MOVE(StatisticsView)
public:
    explicit StatisticsView(VacancySqlModel* model, QWidget* parent = nullptr);

public slots:
    void refresh();

private:
    void rebuildCharts();   // safely removes old charts before rebuilding
    QtCharts::QChartView* buildStatusPie();
    QtCharts::QChartView* buildMonthlyBar();
    QtCharts::QChartView* buildSalaryHist();

    VacancySqlModel*      m_model;
    QHBoxLayout*          m_layout{};
    QtCharts::QChartView* m_pieView{};
    QtCharts::QChartView* m_barView{};
    QtCharts::QChartView* m_histView{};
};
