#pragma once
#include <QWidget>

class VacancySqlModel;
class VacancyFilterModel;
class QTableView;
class QLineEdit;
class QComboBox;
class QPushButton;
class QHBoxLayout;

// Vacancy table + filter toolbar.
class VacancyView final : public QWidget {
    Q_OBJECT
public:
    explicit VacancyView(VacancySqlModel* model, QWidget* parent = nullptr);

signals:
    void vacancyDoubleClicked(int sourceRow);
    void refreshRequested();

private slots:
    void onSearch(const QString& text);
    void onStatusFilter(int idx);
    void onDoubleClick(const QModelIndex& proxyIdx);

private:
    /// Builds the search/filter/refresh toolbar and wires its signals.
    [[nodiscard]] QHBoxLayout* setupToolbar();
    /// Builds the vacancy table view, its columns and delegate.
    void setupTable();

    VacancySqlModel*    m_srcModel;
    VacancyFilterModel* m_filterModel;
    QTableView*         m_table;
    QLineEdit*          m_searchEdit;
    QComboBox*          m_statusCombo;
};
