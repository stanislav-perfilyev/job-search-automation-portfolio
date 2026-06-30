#pragma once
#include <QDialog>
#include <QStringList>
#include <QVector>

class ProcessRunner;
class QComboBox;
class QLineEdit;
class QPushButton;

struct ScriptDef {
    QString     label;
    QString     program;
    QStringList args;
    QString     workDir;
};

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
