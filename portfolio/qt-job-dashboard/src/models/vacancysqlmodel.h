#pragma once
#include "ivacancymodel.h"
#include <QMap>
#include <QString>

// Concrete SQL-backed model (PostgreSQL via QPSQL driver).
// Manages its own named DB connection; safe to re-connect.
class VacancySqlModel final : public IVacancyModel {
    Q_OBJECT
    Q_DISABLE_COPY_MOVE(VacancySqlModel)
public:
    static constexpr char kConnectionName[] = "dashboard_main";

    explicit VacancySqlModel(QObject* parent = nullptr);
    ~VacancySqlModel() override;

    // ── IVacancyModel ─────────────────────────────────────────
    [[nodiscard]] bool    refresh()                          override;
    [[nodiscard]] int     totalCount()                 const override;
    [[nodiscard]] int     countByStatus(const QString& s)   const override;
    [[nodiscard]] QString healthCheck()                const override;

    // ── QAbstractTableModel ───────────────────────────────────
    [[nodiscard]] int          rowCount   (const QModelIndex& parent = {}) const override;
    [[nodiscard]] int          columnCount(const QModelIndex& parent = {}) const override;
    QVariant     data       (const QModelIndex& index, int role = Qt::DisplayRole) const override;
    QVariant     headerData (int section, Qt::Orientation o, int role = Qt::DisplayRole) const override;
    [[nodiscard]] bool         setData    (const QModelIndex& index, const QVariant& value, int role = Qt::EditRole) override;
    Qt::ItemFlags flags     (const QModelIndex& index) const override;

    // Idempotent: removes old named connection before adding a new one.
    [[nodiscard]] static bool connectDatabase(const QString& host,
                                             const QString& db,
                                             const QString& user,
                                             const QString& password,
                                             int port = 5432);

private:
    // Editable columns mapped to DB field names (whitelist — prevents injection).
    static const QMap<int, QString> s_editableFields;
    static const QStringList        s_headers;

    struct Row {
        int     id{};
        QString date, title, company, source, status;
        int     salaryMin{}, salaryMax{};
        QString currency, templateUsed, url, notes;

        // Allows QCOMPARE in tests
        bool operator==(const Row& o) const noexcept {
            return id == o.id && title == o.title && company == o.company;
        }
    };

    QVector<Row>        m_rows;
    QMap<QString, int>  m_statusCount;
};
