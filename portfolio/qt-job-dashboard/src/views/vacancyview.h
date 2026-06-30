#pragma once
#include <QWidget>

class VacancySqlModel;
class VacancyFilterModel;
class QTableView;
class QLineEdit;
class QComboBox;
class QPushButton;

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
    VacancySqlModel*    m_srcModel;
    VacancyFilterModel* m_filterModel;
    QTableView*         m_table;
    QLineEdit*          m_searchEdit;
    QComboBox*          m_statusCombo;
};
