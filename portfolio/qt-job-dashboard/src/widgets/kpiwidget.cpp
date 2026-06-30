#include "kpiwidget.h"
#include <QLabel>
#include <QVBoxLayout>

KpiWidget::KpiWidget(const QString& label, const QString& accent, QWidget* parent)
    : QFrame(parent), m_accent(accent)
{
    setFrameShape(QFrame::StyledPanel);
    setObjectName("KpiCard");

    auto* root     = new QVBoxLayout(this);
    auto* lbl      = new QLabel(label, this);
    m_valueLabel   = new QLabel("—", this);
    m_subtitleLabel = new QLabel(this);
    m_subtitleLabel->setObjectName("KpiSubtitle");
    m_subtitleLabel->hide();

    lbl->setObjectName("KpiLabel");
    m_valueLabel->setObjectName("KpiValue");
    m_valueLabel->setStyleSheet(QString("color: %1; font-size: 36px; font-weight: bold;").arg(accent));

    root->addWidget(lbl);
    root->addWidget(m_valueLabel);
    root->addWidget(m_subtitleLabel);
    root->setContentsMargins(16, 12, 16, 12);
}

void KpiWidget::setValue(int value)
{
    m_valueLabel->setText(QString::number(value));
}

void KpiWidget::setSubtitle(const QString& text)
{
    m_subtitleLabel->setText(text);
    m_subtitleLabel->setVisible(!text.isEmpty());
}
