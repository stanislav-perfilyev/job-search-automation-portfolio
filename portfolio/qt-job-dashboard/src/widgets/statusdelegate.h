#pragma once
#include <QStyledItemDelegate>

// Paints table rows with status-based background colors.
class StatusDelegate final : public QStyledItemDelegate {
    Q_OBJECT
public:
    explicit StatusDelegate(int statusColumn, QObject* parent = nullptr);
    void paint(QPainter* painter, const QStyleOptionViewItem& option,
               const QModelIndex& index) const override;

private:
    int m_statusCol;
};
