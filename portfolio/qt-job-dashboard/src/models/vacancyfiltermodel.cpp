#include "vacancyfiltermodel.h"
#include "ivacancymodel.h"

VacancyFilterModel::VacancyFilterModel(QObject* parent)
    : QSortFilterProxyModel(parent)
{
    setFilterCaseSensitivity(Qt::CaseInsensitive);
    setSortCaseSensitivity(Qt::CaseInsensitive);
}

void VacancyFilterModel::setTextFilter(const QString& text)
{
    m_text = text;
    invalidateFilter();
}

void VacancyFilterModel::setStatusFilter(const QString& status)
{
    m_status = status;
    invalidateFilter();
}

bool VacancyFilterModel::filterAcceptsRow(int sourceRow, const QModelIndex& sourceParent) const
{
    auto* src = sourceModel();
    if (!src) return true;

    // Status filter
    if (!m_status.isEmpty()) {
        auto idx = src->index(sourceRow, IVacancyModel::ColStatus, sourceParent);
        if (src->data(idx).toString() != m_status)
            return false;
    }

    // Text filter: search title + company
    if (!m_text.isEmpty()) {
        auto idxTitle   = src->index(sourceRow, IVacancyModel::ColTitle,   sourceParent);
        auto idxCompany = src->index(sourceRow, IVacancyModel::ColCompany, sourceParent);
        const bool hit  = src->data(idxTitle).toString().contains(m_text, Qt::CaseInsensitive)
                       || src->data(idxCompany).toString().contains(m_text, Qt::CaseInsensitive);
        if (!hit) return false;
    }

    return true;
}
