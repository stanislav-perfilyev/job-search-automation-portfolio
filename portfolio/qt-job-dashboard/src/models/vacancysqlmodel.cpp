#include "vacancysqlmodel.h"
#include "utils/logging.h"
#include "utils/dberror.h"
#include "utils/status.h"
#include <QSqlDatabase>
#include <QSqlQuery>
#include <QSqlError>
#include <QScopeGuard>   // Qt 5.12+ / Qt6

// ── Static members ────────────────────────────────────────────
const QStringList VacancySqlModel::s_headers = {
    "Дата", "Вакансия", "Компания", "Источник", "Статус",
    "Зарплата от", "Зарплата до", "Валюта", "Шаблон", "URL", "Заметки"
};

// Whitelist: only these columns may be edited. Field name is the DB column.
const QMap<int, QString> VacancySqlModel::s_editableFields = {
    { IVacancyModel::ColTitle,   "title"   },
    { IVacancyModel::ColCompany, "company" },
    { IVacancyModel::ColStatus,  "status"  },
    { IVacancyModel::ColNotes,   "notes"   },
};

// ── Construction ──────────────────────────────────────────────
VacancySqlModel::VacancySqlModel(QObject* parent)
    : IVacancyModel(parent)
{
    // Do NOT call refresh() here — DB may not be connected yet.
    // Caller (MainWindow) calls refresh() after connectDatabase().
}

VacancySqlModel::~VacancySqlModel() = default;

// ── Static: (re)connect DB ────────────────────────────────────
bool VacancySqlModel::connectDatabase(const QString& host, const QString& db,
                                      const QString& user, const QString& password,
                                      int port)
{
    // Remove stale named connection to avoid Qt duplicate-connection warning.
    if (QSqlDatabase::contains(kConnectionName))
        QSqlDatabase::removeDatabase(kConnectionName);

    QSqlDatabase conn = QSqlDatabase::addDatabase("QPSQL", kConnectionName);
    conn.setHostName(host);
    conn.setDatabaseName(db);
    conn.setUserName(user);
    conn.setPassword(password);
    conn.setPort(port);
    conn.setConnectOptions("sslmode=require");

    if (!conn.open()) {
        qCCritical(lcDb) << "Connect failed:" << conn.lastError().text();
        return false;
    }
    qCInfo(lcDb) << "Connected to" << host << "/" << db;
    return true;
}

// ── IVacancyModel ─────────────────────────────────────────────
bool VacancySqlModel::refresh()
{
    QSqlDatabase conn = QSqlDatabase::database(kConnectionName);
    if (!conn.isOpen()) {
        const QString msg = "refresh() called but DB not connected";
        qCWarning(lcDb) << msg;
        emit error(msg);
        return false;
    }

    QSqlQuery q(conn);
    q.prepare(
        "SELECT id, CAST(date AS TEXT), title, company, source, status, "
        "       salary_min, salary_max, currency, template_used, url, notes "
        "FROM vacancies "
        "ORDER BY date DESC, company ASC"
    );

    if (!q.exec()) {
        const QString msg = "Query failed: " + q.lastError().text();
        qCWarning(lcDb) << msg;
        emit error(msg);
        return false;
    }

    // RAII: guarantee endResetModel() even if an exception propagates.
    beginResetModel();
    auto guard = qScopeGuard([this]{ endResetModel(); });

    m_rows.clear();
    m_statusCount.clear();

    while (q.next()) {
        Row r;
        r.id          = q.value(0).toInt();
        r.date        = q.value(1).toString();
        r.title       = q.value(2).toString();
        r.company     = q.value(3).toString();
        r.source      = q.value(4).toString();
        r.status      = q.value(5).toString();
        r.salaryMin   = q.value(6).toInt();
        r.salaryMax   = q.value(7).toInt();
        r.currency    = q.value(8).toString();
        r.templateUsed = q.value(9).toString();
        r.url         = q.value(10).toString();
        r.notes       = q.value(11).toString();
        m_statusCount[r.status]++;
        m_rows.append(std::move(r));
    }

    qCDebug(lcDb) << "Loaded" << m_rows.size() << "vacancies";
    return true;
}

int VacancySqlModel::totalCount() const noexcept { return m_rows.size(); }

int VacancySqlModel::countByStatus(const QString& status) const
{
    return m_statusCount.value(status, 0);
}

QString VacancySqlModel::healthCheck() const
{
    QSqlDatabase conn = QSqlDatabase::database(kConnectionName);
    if (!conn.isOpen()) return "DB not connected";

    QSqlQuery q(conn);
    if (!q.exec("SELECT 1")) return "DB ping failed: " + q.lastError().text();

    return {};   // empty = healthy
}

// ── QAbstractTableModel ───────────────────────────────────────
int VacancySqlModel::rowCount(const QModelIndex& parent) const
{
    return parent.isValid() ? 0 : static_cast<int>(m_rows.size());
}

int VacancySqlModel::columnCount(const QModelIndex& parent) const
{
    return parent.isValid() ? 0 : ColCount;
}

QVariant VacancySqlModel::data(const QModelIndex& index, int role) const
{
    if (!index.isValid()
        || index.row() < 0
        || index.row() >= static_cast<int>(m_rows.size()))
        return {};

    if (role != Qt::DisplayRole && role != Qt::EditRole && role != Qt::UserRole)
        return {};

    const Row& r = m_rows[index.row()];
    switch (index.column()) {
    case ColDate:      return r.date;
    case ColTitle:     return r.title;
    case ColCompany:   return r.company;
    case ColSource:    return r.source;
    case ColStatus:    return r.status;
    case ColSalaryMin: return r.salaryMin > 0 ? QVariant(r.salaryMin) : QVariant{};
    case ColSalaryMax: return r.salaryMax > 0 ? QVariant(r.salaryMax) : QVariant{};
    case ColCurrency:  return r.currency;
    case ColTemplate:  return r.templateUsed;
    case ColUrl:       return r.url;
    case ColNotes:     return r.notes;
    default:           return {};
    }
}

QVariant VacancySqlModel::headerData(int section, Qt::Orientation orientation, int role) const
{
    if (role != Qt::DisplayRole) return {};
    if (orientation == Qt::Horizontal) {
        if (section >= 0 && section < s_headers.size())
            return s_headers[section];
    } else {
        return section + 1;
    }
    return {};
}

bool VacancySqlModel::setData(const QModelIndex& index, const QVariant& value, int role)
{
    if (role != Qt::EditRole || !index.isValid()
        || index.row() < 0 || index.row() >= static_cast<int>(m_rows.size()))
        return false;

    // Whitelist check — only allowed fields
    const auto it = s_editableFields.find(index.column());
    if (it == s_editableFields.end()) return false;
    const QString& field = it.value();   // safe: from static map, not user input

    Row& r = m_rows[index.row()];

    QSqlDatabase conn = QSqlDatabase::database(kConnectionName);
    QSqlQuery q(conn);
    q.prepare(QString("UPDATE vacancies SET %1 = :val WHERE id = :id").arg(field));
    q.bindValue(":val", value);
    q.bindValue(":id",  r.id);

    if (!q.exec()) {
        const QString msg = "setData failed: " + q.lastError().text();
        qCWarning(lcDb) << msg;
        emit error(msg);
        return false;
    }

    // Update cache
    switch (index.column()) {
    case ColTitle:   r.title   = value.toString(); break;
    case ColCompany: r.company = value.toString(); break;
    case ColStatus:  r.status  = value.toString(); break;
    case ColNotes:   r.notes   = value.toString(); break;
    default: break;
    }

    emit dataChanged(index, index, {role});
    return true;
}

Qt::ItemFlags VacancySqlModel::flags(const QModelIndex& index) const
{
    auto f = QAbstractTableModel::flags(index);
    if (s_editableFields.contains(index.column()))
        f |= Qt::ItemIsEditable;
    return f;
}
