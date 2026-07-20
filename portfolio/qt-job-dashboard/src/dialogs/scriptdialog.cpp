#include "scriptdialog.h"
#include "widgets/processrunner.h"
#include <QComboBox>
#include <QLineEdit>
#include <QPushButton>
#include <QLabel>
#include <QFormLayout>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QDialogButtonBox>
#include <QMessageBox>

namespace {
constexpr int kDialogMinWidth  = 700;
constexpr int kDialogMinHeight = 480;
constexpr int kFormStretch     = 1;
constexpr int kOutputStretch   = 1;
}  // namespace

ScriptDialog::ScriptDialog(const QString& projectRoot, QWidget* parent)
    : QDialog(parent)
{
    setWindowTitle("Запустить скрипт");
    setMinimumSize(kDialogMinWidth, kDialogMinHeight);

    buildScriptList(projectRoot);

    m_scriptCombo = new QComboBox(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    for (const auto& s : std::as_const(m_scripts))
        m_scriptCombo->addItem(s.label);

    m_argsEdit = new QLineEdit(this);  // NOLINT(cppcoreguidelines-owning-memory)
    m_argsEdit->setPlaceholderText("Дополнительные аргументы (необязательно)");

    m_runBtn = new QPushButton("▶ Запустить", this);  // NOLINT(cppcoreguidelines-owning-memory)
    m_runBtn->setStyleSheet("background:#0F5132; color:#E0E0E0; padding:5px 18px;");

    auto* closeBtn = new QDialogButtonBox(QDialogButtonBox::Close, this);  // NOLINT(cppcoreguidelines-owning-memory)

    m_runner = new ProcessRunner(this);  // NOLINT(cppcoreguidelines-owning-memory)

    auto* form = new QFormLayout;  // NOLINT(cppcoreguidelines-owning-memory) — reparented by addLayout
    form->addRow("Скрипт:", m_scriptCombo);
    form->addRow("Аргументы:", m_argsEdit);

    auto* topRow = new QHBoxLayout;  // NOLINT(cppcoreguidelines-owning-memory) — reparented by addLayout
    topRow->addLayout(form, kFormStretch);
    topRow->addWidget(m_runBtn, 0, Qt::AlignBottom);

    auto* root = new QVBoxLayout(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    root->addLayout(topRow);
    root->addWidget(new QLabel("Вывод:", this));  // NOLINT(cppcoreguidelines-owning-memory)
    root->addWidget(m_runner, kOutputStretch);
    root->addWidget(closeBtn);

    connect(m_runBtn,      &QPushButton::clicked,
            this, &ScriptDialog::onRun);
    connect(m_scriptCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &ScriptDialog::onScriptChanged);
    connect(m_runner, &ProcessRunner::finished,
            this, &ScriptDialog::onFinished);
    connect(m_runner, &ProcessRunner::processError,
            this, [this](const QString& msg){
                QMessageBox::warning(this, "Ошибка процесса", msg);
            });
    connect(closeBtn, &QDialogButtonBox::rejected, this, &QDialog::reject);
}

void ScriptDialog::buildScriptList(const QString& root)
{
#ifdef Q_OS_WIN
    const QString py = "python";
#else
    const QString py = "python3";
#endif

    m_scripts = {
        { "sync_to_sheets.py — зеркало PG → Sheets",
          py, {"sync_to_sheets.py"}, root },
        { "skill_gap_report.py — анализ пробелов навыков",
          py, {"skill_gap_report.py"}, root },
        { "report.py — статистика из БД",
          py, {"report.py"}, root },
        { "cover_letter.py — сгенерировать сопроводительное",
          py, {"cover_letter.py"}, root },
        { "kpi_report.py — еженедельный KPI",
          py, {"kpi_report.py"}, root },
        { "morning_brief.py — утренний брифинг",
          py, {"morning_brief.py"}, root },
        { "follow_up.py — follow-up по просроченным",
          py, {"follow_up.py"}, root },
        { "Кастомная команда…",    // must stay last — isCustom() relies on index
          py, {}, root },
    };
}

bool ScriptDialog::isCustom() const
{
    return m_scriptCombo->currentIndex() == m_scripts.size() - 1;
}

void ScriptDialog::onScriptChanged(int /*index*/)
{
    m_argsEdit->setPlaceholderText(isCustom()
        ? "script.py --arg value"
        : "Дополнительные аргументы (необязательно)");
    if (isCustom()) m_argsEdit->clear();
}

void ScriptDialog::onRun()
{
    if (m_runner->isRunning()) return;

    ScriptDef def = m_scripts[m_scriptCombo->currentIndex()];
    const QStringList extra =
        m_argsEdit->text().trimmed().split(' ', Qt::SkipEmptyParts);

    if (isCustom()) {
        // Custom mode: argsEdit contains the full script + args
        if (extra.isEmpty()) {
            QMessageBox::warning(this, "Нет команды",
                "Введите имя скрипта и аргументы в поле «Аргументы».");
            return;
        }
        def.args = extra;  // replace, not append
    } else {
        def.args += extra; // append extra args to preset
    }

    m_runBtn->setEnabled(false);
    m_runner->clear();
    m_runner->start(def.program, def.args, def.workDir);
}

void ScriptDialog::onFinished(int /*code*/)
{
    m_runBtn->setEnabled(true);
}
