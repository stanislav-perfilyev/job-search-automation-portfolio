#pragma once
#include <QDialog>

class IVacancyModel;
class QTextEdit;
class QPushButton;

// Self-diagnostics dialog: checks DB, QSql driver, disk space, model state.
// Launched from Help → Диагностика system.
class DiagnosticsDialog final : public QDialog {
    Q_OBJECT
    Q_DISABLE_COPY_MOVE(DiagnosticsDialog)
public:
    explicit DiagnosticsDialog(IVacancyModel* model, QWidget* parent = nullptr);

private slots:
    void runDiagnostics();

private:
    struct Check {
        QString name;
        bool    passed;
        QString detail;
    };

    [[nodiscard]] QVector<Check> collectChecks() const;
    void renderReport(const QVector<Check>& checks);

    IVacancyModel* m_model;
    QTextEdit*     m_output;
    QPushButton*   m_refreshBtn;
};
