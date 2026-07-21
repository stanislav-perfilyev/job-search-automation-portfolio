#pragma once
#include <QDialog>

class QLineEdit;
class QSpinBox;

/// Modal dialog for editing and persisting the PostgreSQL connection
/// settings used by the dashboard (stored via QSettings("JobDashboard","db")).
class SettingsDialog final : public QDialog {
    Q_OBJECT
public:
    explicit SettingsDialog(QWidget* parent = nullptr);

    struct DbConfig {
        QString host, database, user, password;
        int port{5432};
    };
    [[nodiscard]] DbConfig config() const;

private:
    QLineEdit* m_host;
    QLineEdit* m_database;
    QLineEdit* m_user;
    QLineEdit* m_password;
    QSpinBox*  m_port;
};
