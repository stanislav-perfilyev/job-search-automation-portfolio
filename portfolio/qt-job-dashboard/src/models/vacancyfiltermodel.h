#pragma once
#include <QSortFilterProxyModel>
#include <QString>

// Multi-column filter proxy: text search + status dropdown.
class VacancyFilterModel final : public QSortFilterProxyModel {
    Q_OBJECT
public:
    explicit VacancyFilterModel(QObject* parent = nullptr);

    void setTextFilter(const QString& text);
    void setStatusFilter(const QString& status);   // empty = all

protected:
    [[nodiscard]] bool filterAcceptsRow(int sourceRow, const QModelIndex& sourceParent) const override;

private:
    QString m_text;
    QString m_status;
};
