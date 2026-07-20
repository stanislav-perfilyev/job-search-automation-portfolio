#include "statisticsview.h"
#include "models/vacancysqlmodel.h"
#include <QHBoxLayout>
#include <QSqlQuery>
#include <QSqlDatabase>
#include <QtCharts/QChartView>
#include <QtCharts/QPieSeries>
#include <QtCharts/QBarSeries>
#include <QtCharts/QBarSet>
#include <QtCharts/QBarCategoryAxis>
#include <QtCharts/QValueAxis>
#include <QtCharts/QChart>

// Qt 6: QT_CHARTS_USE_NAMESPACE is a no-op; QChartView et al. are in the global namespace.

StatisticsView::StatisticsView(VacancySqlModel* model, QWidget* parent)
    : QWidget(parent), m_model(model)
{
    m_layout = new QHBoxLayout(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    rebuildCharts();
}

void StatisticsView::refresh()
{
    rebuildCharts();
}

void StatisticsView::rebuildCharts()
{
    // Remove and delete old charts properly (avoid dangling layout refs).
    // takeAt() transfers ownership of the QLayoutItem to us — the standard
    // Qt idiom for clearing a layout requires this explicit manual delete.
    while (QLayoutItem* item = m_layout->takeAt(0)) {
        delete item->widget();  // NOLINT(cppcoreguidelines-owning-memory)
        delete item;            // NOLINT(cppcoreguidelines-owning-memory)
    }

    m_pieView  = buildStatusPie();
    m_barView  = buildMonthlyBar();
    m_histView = buildSalaryHist();

    m_layout->addWidget(m_pieView);
    m_layout->addWidget(m_barView);
    m_layout->addWidget(m_histView);
}

static QSqlQuery execChart(const QString& sql)
{
    QSqlQuery q(QSqlDatabase::database(VacancySqlModel::kConnectionName));
    q.exec(sql);
    return q;
}

QChartView* StatisticsView::buildStatusPie()
{
    auto* series = new QPieSeries;  // NOLINT(cppcoreguidelines-owning-memory) — ownership taken by chart->addSeries() below
    auto q = execChart("SELECT status, COUNT(*) FROM vacancies GROUP BY status ORDER BY 2 DESC");
    while (q.next())
        series->append(q.value(0).toString(), q.value(1).toReal());

    for (auto* slice : series->slices())
        slice->setLabel(QString("%1\n%2").arg(slice->label()).arg((int)slice->value()));

    auto* chart = new QChart;  // NOLINT(cppcoreguidelines-owning-memory) — ownership taken by QChartView below
    chart->addSeries(series);
    chart->setTitle("Статусы");
    chart->setTheme(QChart::ChartThemeDark);
    chart->legend()->setAlignment(Qt::AlignRight);

    auto* view = new QChartView(chart, this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    view->setRenderHint(QPainter::Antialiasing);
    return view;
}

QChartView* StatisticsView::buildMonthlyBar()
{
    auto* set = new QBarSet("Отклики");  // NOLINT(cppcoreguidelines-owning-memory) — ownership taken by series->append() below
    QStringList categories;

    auto q = execChart(
        "SELECT TO_CHAR(date,'YYYY-MM') AS mo, COUNT(*) "
        "FROM vacancies GROUP BY mo ORDER BY mo DESC LIMIT 6"
    );
    QVector<QPair<QString,int>> rows;
    while (q.next())
        rows.prepend({q.value(0).toString(), q.value(1).toInt()});

    for (auto& [mo, cnt] : rows) {
        categories << mo;
        *set << cnt;
    }

    auto* series = new QBarSeries;  // NOLINT(cppcoreguidelines-owning-memory) — ownership taken by chart->addSeries() below
    series->append(set);
    auto* axisX = new QBarCategoryAxis; axisX->append(categories);  // NOLINT(cppcoreguidelines-owning-memory) — ownership taken by chart->addAxis() below
    auto* axisY = new QValueAxis;       axisY->setLabelFormat("%d");  // NOLINT(cppcoreguidelines-owning-memory)

    auto* chart = new QChart;  // NOLINT(cppcoreguidelines-owning-memory) — ownership taken by QChartView below
    chart->addSeries(series);
    chart->addAxis(axisX, Qt::AlignBottom);
    chart->addAxis(axisY, Qt::AlignLeft);
    series->attachAxis(axisX);
    series->attachAxis(axisY);
    chart->setTitle("Отклики по месяцам");
    chart->setTheme(QChart::ChartThemeDark);
    chart->legend()->hide();

    auto* view = new QChartView(chart, this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    view->setRenderHint(QPainter::Antialiasing);
    return view;
}

QChartView* StatisticsView::buildSalaryHist()
{
    constexpr int BUCKET = 50000;
    QMap<int,int> buckets;
    auto q = execChart("SELECT salary_min FROM vacancies WHERE salary_min > 0");
    while (q.next()) {
        int b = (q.value(0).toInt() / BUCKET) * BUCKET;
        buckets[b]++;
    }

    auto* set = new QBarSet("Вакансии");  // NOLINT(cppcoreguidelines-owning-memory) — ownership taken by series->append() below
    QStringList cats;
    for (auto it = buckets.cbegin(); it != buckets.cend(); ++it) {
        cats << QString("%1k").arg(it.key()/1000);
        *set << it.value();
    }

    auto* series = new QBarSeries; series->append(set);  // NOLINT(cppcoreguidelines-owning-memory) — ownership taken by chart->addSeries() below
    auto* axisX  = new QBarCategoryAxis; axisX->append(cats);  // NOLINT(cppcoreguidelines-owning-memory) — ownership taken by chart->addAxis() below
    auto* axisY  = new QValueAxis;  // NOLINT(cppcoreguidelines-owning-memory)

    auto* chart = new QChart;  // NOLINT(cppcoreguidelines-owning-memory) — ownership taken by QChartView below
    chart->addSeries(series);
    chart->addAxis(axisX, Qt::AlignBottom);
    chart->addAxis(axisY, Qt::AlignLeft);
    series->attachAxis(axisX);
    series->attachAxis(axisY);
    chart->setTitle("Распределение зарплат");
    chart->setTheme(QChart::ChartThemeDark);
    chart->legend()->hide();

    auto* view = new QChartView(chart, this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    view->setRenderHint(QPainter::Antialiasing);
    return view;
}
