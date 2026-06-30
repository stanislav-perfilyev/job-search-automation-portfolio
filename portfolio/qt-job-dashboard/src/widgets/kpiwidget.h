#pragma once
#include <QFrame>
#include <QString>

class QLabel;

// Single KPI card: label + big number + optional subtitle.
class KpiWidget final : public QFrame {
    Q_OBJECT
public:
    explicit KpiWidget(const QString& label, const QString& accent = "#4A9EFF",
                       QWidget* parent = nullptr);

    void setValue(int value);
    void setSubtitle(const QString& text);

private:
    QLabel* m_valueLabel;
    QLabel* m_subtitleLabel;
    QString m_accent;
};
