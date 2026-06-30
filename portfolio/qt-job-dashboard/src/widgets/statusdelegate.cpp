#include "statusdelegate.h"
#include <QPainter>
#include <QApplication>
#include <QMap>

static const QMap<QString, QColor> STATUS_COLOR = {
    {"Откликнулся",  QColor(0x1E,0x3A,0x5F, 220)},   // dark-blue
    {"Интервью",     QColor(0x2E,0x5E,0x2E, 220)},   // dark-green
    {"Оффер",        QColor(0x5C,0x3E,0x00, 220)},   // gold-dark
    {"Отказ",        QColor(0x55,0x1C,0x1C, 220)},   // dark-red
    {"Просмотрено",  QColor(0x1E,0x1E,0x3A, 220)},   // muted
};

StatusDelegate::StatusDelegate(int statusColumn, QObject* parent)
    : QStyledItemDelegate(parent), m_statusCol(statusColumn) {}

void StatusDelegate::paint(QPainter* painter, const QStyleOptionViewItem& option,
                           const QModelIndex& index) const
{
    QStyleOptionViewItem opt = option;
    initStyleOption(&opt, index);

    // Grab status from same row
    const QModelIndex statusIdx = index.sibling(index.row(), m_statusCol);
    const QString status = statusIdx.data().toString();

    if (STATUS_COLOR.contains(status)) {
        opt.backgroundBrush = STATUS_COLOR[status];
    }

    QApplication::style()->drawControl(QStyle::CE_ItemViewItem, &opt, painter);
}
