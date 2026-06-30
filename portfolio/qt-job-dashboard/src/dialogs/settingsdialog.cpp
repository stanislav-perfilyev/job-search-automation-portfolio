#include "settingsdialog.h"
#include <QLineEdit>
#include <QSpinBox>
#include <QFormLayout>
#include <QDialogButtonBox>
#include <QVBoxLayout>
#include <QGroupBox>
#include <QSettings>

SettingsDialog::SettingsDialog(QWidget* parent)
    : QDialog(parent)
{
    setWindowTitle("Настройки подключения");
    setMinimumWidth(400);

    m_host     = new QLineEdit(this);
    m_database = new QLineEdit(this);
    m_user     = new QLineEdit(this);
    m_password = new QLineEdit(this);
    m_password->setEchoMode(QLineEdit::Password);
    m_port     = new QSpinBox(this);
    m_port->setRange(1, 65535);
    m_port->setValue(5432);

    // Load saved values
    QSettings s("JobDashboard", "db");
    m_host->setText(s.value("host").toString());
    m_database->setText(s.value("database").toString());
    m_user->setText(s.value("user").toString());
    m_password->setText(s.value("password").toString());
    m_port->setValue(s.value("port", 5432).toInt());

    auto* group = new QGroupBox("PostgreSQL", this);
    auto* form  = new QFormLayout(group);
    form->addRow("Host:",     m_host);
    form->addRow("Database:", m_database);
    form->addRow("User:",     m_user);
    form->addRow("Password:", m_password);
    form->addRow("Port:",     m_port);

    auto* btnBox = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, this);
    auto* root   = new QVBoxLayout(this);
    root->addWidget(group);
    root->addWidget(btnBox);

    connect(btnBox, &QDialogButtonBox::accepted, [this, &s]{
        s.setValue("host",     m_host->text());
        s.setValue("database", m_database->text());
        s.setValue("user",     m_user->text());
        s.setValue("password", m_password->text());
        s.setValue("port",     m_port->value());
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
