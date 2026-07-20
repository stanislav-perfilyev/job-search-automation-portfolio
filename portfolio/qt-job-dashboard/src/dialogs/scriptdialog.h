#pragma once
#include <QDialog>
#include <QStringList>
#include <QVector>

class ProcessRunner;
class QComboBox;
class QLineEdit;
class QPushButton;

/// One runnable helper script: display label, interpreter, default args and
/// working directory. The last entry in ScriptDialog's preset list is a
/// free-form "custom command" slot (see ScriptDialog::isCustom()).
struct ScriptDef {
    QString     label;
    QString     program;
    QStringList args;
    QString     workDir;
};

/// Dialog that lists the project's helper Python scripts (sync, reports,
/// KPI, cover letters, …), runs the selected one via ProcessRunner and
/// streams its output live.
class ScriptDialog final : public QDialog {
    Q_OBJECT
    Q_DISABLE_COPY_MOVE(ScriptDialog)
public:
    explicit ScriptDialog(const QString& projectRoot, QWidget* parent = nullptr);

private slots:
    void onRun();
    void onScriptChanged(int index);
    void onFinished(int code);

private:
    void buildScriptList(const QString& root);
    [[nodiscard]] bool isCustom() const;

    QComboBox*         m_scriptCombo{};
    QLineEdit*         m_argsEdit{};
    QPushButton*       m_runBtn{};
    ProcessRunner*     m_runner{};
    QVector<ScriptDef> m_scripts;
};
