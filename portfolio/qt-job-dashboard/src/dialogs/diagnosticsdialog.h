#pragma once
#include <QDialog>

class IVacancyModel;
class QTextEdit;
class QPushButton;

/**
 * @class DiagnosticsDialog
 * @brief Self-diagnostics dialog: checks DB, QSql driver, disk space, model state.
 *
 * Launched from Help → Диагностика. Each check runs independently so one
 * failure (e.g. no DB connection) doesn't block the others from reporting.
 */
class DiagnosticsDialog final : public QDialog {
    Q_OBJECT
    Q_DISABLE_COPY_MOVE(DiagnosticsDialog)
public:
    explicit DiagnosticsDialog(IVacancyModel* model, QWidget* parent = nullptr);

private slots:
    void runDiagnostics();

private:
    /// Result of a single diagnostic check.
    struct Check {
        QString name;
        bool    passed;
        QString detail;
    };

    [[nodiscard]] QVector<Check> collectChecks() const;
    [[nodiscard]] Check checkDriverAvailable() const;
    [[nodiscard]] Check checkConnectionOpen() const;
    [[nodiscard]] Check checkDbPing() const;
    [[nodiscard]] Check checkModelLoaded() const;
    [[nodiscard]] Check checkModelHealth() const;
    [[nodiscard]] Check checkDiskSpace() const;
    [[nodiscard]] Check checkQtVersion() const;
    void renderReport(const QVector<Check>& checks);

    IVacancyModel* m_model;
    QTextEdit*     m_output;
    QPushButton*   m_refreshBtn;
};
