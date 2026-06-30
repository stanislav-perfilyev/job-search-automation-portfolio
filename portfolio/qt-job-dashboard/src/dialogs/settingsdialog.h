#pragma once
#include <QDialog>

class QLineEdit;
class QSpinBox;

class SettingsDialog final : public QDialog {
    Q_OBJECT
public:
    explicit SettingsDialog(QWidget* parent = nullptr);

    struct DbConfig {
        QString host, database, user, password;
        int port{5432};
    };
    DbConfig config() const;
    void     setConfig(const DbConfig& cfg);

private:
    QLineEdit* m_host;
    QLineEdit* m_database;
    QLineEdit* m_user;
    QLineEdit* m_password;
    QSpinBox*  m_port;
};
