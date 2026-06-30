#pragma once
#include <QDialog>

class VacancySqlModel;
class QLabel;
class QTextEdit;
class QPushButton;

// Read-only detail view of one vacancy row.
class VacancyDetailDialog final : public QDialog {
    Q_OBJECT
public:
    VacancyDetailDialog(VacancySqlModel* model, int row, QWidget* parent = nullptr);

private:
    void populate(VacancySqlModel* model, int row);
    QLabel*    m_titleLabel;
    QLabel*    m_metaLabel;
    QTextEdit* m_notesEdit;
    QPushButton* m_urlBtn;
    QString    m_url;
};
