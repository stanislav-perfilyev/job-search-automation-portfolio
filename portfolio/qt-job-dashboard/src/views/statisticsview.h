#pragma once
#include <QWidget>

class VacancySqlModel;
class QHBoxLayout;
class QChartView;   // Qt 6: QChartView is in the global namespace (QtCharts namespace removed)

class StatisticsView final : public QWidget {
    Q_OBJECT
    Q_DISABLE_COPY_MOVE(StatisticsView)
public:
    explicit StatisticsView(VacancySqlModel* model, QWidget* parent = nullptr);

public slots:
    void refresh();

private:
    void rebuildCharts();   // safely removes old charts before rebuilding
    QChartView* buildStatusPie();
    QChartView* buildMonthlyBar();
    QChartView* buildSalaryHist();

    VacancySqlModel* m_model;
    QHBoxLayout*     m_layout{};
    QChartView*      m_pieView{};
    QChartView*      m_barView{};
    QChartView*      m_histView{};
};
