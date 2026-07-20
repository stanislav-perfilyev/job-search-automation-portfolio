#include "settingsdialog.h"
#include <QLineEdit>
#include <QSpinBox>
#include <QFormLayout>
#include <QDialogButtonBox>
#include <QVBoxLayout>
#include <QGroupBox>
#include <QSettings>

namespace {
constexpr int kDialogMinWidth = 400;
constexpr int kPortMin        = 1;
constexpr int kPortMax        = 65535;
constexpr int kDefaultPort    = 5432;
const char* const kSettingsOrg = "JobDashboard";
const char* const kSettingsApp = "db";
}  // namespace

SettingsDialog::SettingsDialog(QWidget* parent)
    : QDialog(parent)
{
    setWindowTitle("Настройки подключения");
    setMinimumWidth(kDialogMinWidth);

    m_host     = new QLineEdit(this);      // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    m_database = new QLineEdit(this);      // NOLINT(cppcoreguidelines-owning-memory)
    m_user     = new QLineEdit(this);      // NOLINT(cppcoreguidelines-owning-memory)
    m_password = new QLineEdit(this);      // NOLINT(cppcoreguidelines-owning-memory)
    m_password->setEchoMode(QLineEdit::Password);
    m_port     = new QSpinBox(this);       // NOLINT(cppcoreguidelines-owning-memory)
    m_port->setRange(kPortMin, kPortMax);
    m_port->setValue(kDefaultPort);

    // Load saved values. `s` is scoped to the constructor only — the OK
    // handler below opens its own QSettings instance rather than capturing
    // this one by reference (it would otherwise dangle after construction).
    const QSettings s(kSettingsOrg, kSettingsApp);
    m_host->setText(s.value("host").toString());
    m_database->setText(s.value("database").toString());
    m_user->setText(s.value("user").toString());
    m_password->setText(s.value("password").toString());
    m_port->setValue(s.value("port", kDefaultPort).toInt());

    auto* group = new QGroupBox("PostgreSQL", this);  // NOLINT(cppcoreguidelines-owning-memory)
    auto* form  = new QFormLayout(group);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    form->addRow("Host:",     m_host);
    form->addRow("Database:", m_database);
    form->addRow("User:",     m_user);
    form->addRow("Password:", m_password);
    form->addRow("Port:",     m_port);

    auto* btnBox = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, this);  // NOLINT(cppcoreguidelines-owning-memory)
    auto* root   = new QVBoxLayout(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    root->addWidget(group);
    root->addWidget(btnBox);

    connect(btnBox, &QDialogButtonBox::accepted, this, [this]{
        QSettings settings(kSettingsOrg, kSettingsApp);
        settings.setValue("host",     m_host->text());
        settings.setValue("database", m_database->text());
        settings.setValue("user",     m_user->text());
        settings.setValue("password", m_password->text());
        settings.setValue("port",     m_port->value());
        accept();
    });
    connect(btnBox, &QDialogButtonBox::rejected, this, &QDialog::reject);
}

SettingsDialog::DbConfig SettingsDialog::config() const
{
    return { m_host->text(), m_database->text(),
             m_user->text(), m_password->text(), m_port->value() };
}

void SettingsDialog::setConfig(const DbConfig& cfg)
{
    m_host->setText(cfg.host);
    m_database->setText(cfg.database);
    m_user->setText(cfg.user);
    m_password->setText(cfg.password);
    m_port->setValue(cfg.port);
}
