#include <QtTest/QtTest>
#include <QSqlDatabase>
#include <QSqlQuery>
#include <QSqlError>
#include "models/vacancysqlmodel.h"
#include "models/vacancyfiltermodel.h"
#include "models/ivacancymodel.h"
#include "utils/status.h"

// ─────────────────────────────────────────────────────────────
// TestVacancyModel
// Uses SQLite in-memory DB on the NAMED connection "dashboard_main"
// so VacancySqlModel::refresh() queries through it (no Neon needed).
// ─────────────────────────────────────────────────────────────
class TestVacancyModel : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();
    void cleanupTestCase();

    // Model basics
    void test_columnCount_always11();
    void test_rowCount_matchesSeededData();
    void test_headerData_nonEmpty();
    void test_headerData_outOfRange();

    // Data access
    void test_data_validIndex();
    void test_data_invalidIndex();
    void test_data_salaryZeroReturnsNull();

    // Status counts
    void test_countByStatus_known();
    void test_countByStatus_unknown();
    void test_totalCount();

    // healthCheck
    void test_healthCheck_connected();

    // Filter proxy
    void test_filterByText_noMatch();
    void test_filterByText_match();
    void test_filterByText_caseInsensitive();
    void test_filterByStatus_knownStatus();
    void test_filterByStatus_all();
    void test_filterCombined_narrowsResult();
    void test_filterReset_restoresRows();

    // Sort
    void test_sort_doesNotCrash();

    // Flags
    void test_flags_editableColumns();
    void test_flags_readOnlyColumns();

private:
    void seedDb();
    QSqlDatabase m_db;
    VacancySqlModel* m_model{};
};

void TestVacancyModel::initTestCase()
{
    // Use the SAME named connection that VacancySqlModel uses internally
    m_db = QSqlDatabase::addDatabase("QSQLITE", VacancySqlModel::kConnectionName);
    m_db.setDatabaseName(":memory:");
    QVERIFY2(m_db.open(), qPrintable(m_db.lastError().text()));

    QSqlQuery q(m_db);
    const bool created = q.exec(
        "CREATE TABLE vacancies ("
        "  id INTEGER PRIMARY KEY,"
        "  date TEXT, title TEXT, company TEXT, source TEXT, status TEXT,"
        "  salary_min INTEGER DEFAULT 0, salary_max INTEGER DEFAULT 0,"
        "  currency TEXT DEFAULT 'RUB',"
        "  template_used TEXT, url TEXT, notes TEXT"
        ")"
    );
    QVERIFY2(created, qPrintable(q.lastError().text()));
    seedDb();

    m_model = new VacancySqlModel;
    QVERIFY(m_model->refresh());
}

void TestVacancyModel::cleanupTestCase()
{
    delete m_model;
    m_db.close();
    QSqlDatabase::removeDatabase(VacancySqlModel::kConnectionName);
}

void TestVacancyModel::seedDb()
{
    QSqlQuery q(m_db);
    struct R { int id; const char* date; const char* title; const char* company;
               const char* source; const char* status; int smin; int smax; };
    const R rows[] = {
        {1,"2024-06-01","C++ Dev",     "EPAM",       "hh.kz",   Status::Applied,   200000,300000},
        {2,"2024-06-02","Qt Engineer", "Kaspersky",  "habr",    Status::Interview, 250000,350000},
        {3,"2024-06-03","Embedded",    "GlobalLogic","hh.kz",   Status::Rejected,       0,     0},
        {4,"2024-06-04","Lead C++",    "Yandex",     "linkedin",Status::Offer,     400000,500000},
        {5,"2024-06-05","C++ Gamedev", "Mail.ru",    "hh.kz",   Status::Viewed,    180000,     0},
    };
    for (const auto& r : rows) {
        q.prepare("INSERT INTO vacancies VALUES(?,?,?,?,?,?,?,?,?,?,?,?)");
        q.addBindValue(r.id);  q.addBindValue(r.date); q.addBindValue(r.title);
        q.addBindValue(r.company); q.addBindValue(r.source); q.addBindValue(r.status);
        q.addBindValue(r.smin); q.addBindValue(r.smax); q.addBindValue("RUB");
        q.addBindValue("A"); q.addBindValue(""); q.addBindValue("note");
        QVERIFY2(q.exec(), qPrintable(q.lastError().text()));
    }
}

// ── Model basics ─────────────────────────────────────────────
void TestVacancyModel::test_columnCount_always11()
{
    QCOMPARE(m_model->columnCount(), (int)IVacancyModel::ColCount);
}

void TestVacancyModel::test_rowCount_matchesSeededData()
{
    QCOMPARE(m_model->rowCount(), 5);
}

void TestVacancyModel::test_headerData_nonEmpty()
{
    for (int c = 0; c < IVacancyModel::ColCount; ++c)
        QVERIFY(!m_model->headerData(c, Qt::Horizontal).toString().isEmpty());
}

void TestVacancyModel::test_headerData_outOfRange()
{
    QCOMPARE(m_model->headerData(-1, Qt::Horizontal), QVariant{});
    QCOMPARE(m_model->headerData(999, Qt::Horizontal), QVariant{});
}

// ── Data access ───────────────────────────────────────────────
void TestVacancyModel::test_data_validIndex()
{
    // Rows are sorted date DESC → row 0 = id5 (2024-06-05)
    const QModelIndex idx = m_model->index(0, IVacancyModel::ColTitle);
    QCOMPARE(m_model->data(idx).toString(), QString("C++ Gamedev"));
}

void TestVacancyModel::test_data_invalidIndex()
{
    QCOMPARE(m_model->data(QModelIndex{}), QVariant{});
    QCOMPARE(m_model->data(m_model->index(999, 0)), QVariant{});
}

void TestVacancyModel::test_data_salaryZeroReturnsNull()
{
    // id3 (Embedded/Отказ) has salary_min=0 → should return null QVariant
    // Find row where title=="Embedded"
    for (int r = 0; r < m_model->rowCount(); ++r) {
        if (m_model->data(m_model->index(r, IVacancyModel::ColTitle)).toString() == "Embedded") {
            QCOMPARE(m_model->data(m_model->index(r, IVacancyModel::ColSalaryMin)), QVariant{});
            return;
        }
    }
    QFAIL("Row 'Embedded' not found");
}

// ── Status counts ─────────────────────────────────────────────
void TestVacancyModel::test_countByStatus_known()
{
    QCOMPARE(m_model->countByStatus(Status::Applied),   1);
    QCOMPARE(m_model->countByStatus(Status::Interview), 1);
    QCOMPARE(m_model->countByStatus(Status::Offer),     1);
    QCOMPARE(m_model->countByStatus(Status::Rejected),  1);
    QCOMPARE(m_model->countByStatus(Status::Viewed),    1);
}

void TestVacancyModel::test_countByStatus_unknown()
{
    QCOMPARE(m_model->countByStatus("НеизвестныйСтатус"), 0);
}

void TestVacancyModel::test_totalCount()
{
    QCOMPARE(m_model->totalCount(), 5);
}

// ── healthCheck ───────────────────────────────────────────────
void TestVacancyModel::test_healthCheck_connected()
{
    QVERIFY2(m_model->healthCheck().isEmpty(),
             qPrintable("healthCheck failed: " + m_model->healthCheck()));
}

// ── Filter proxy ──────────────────────────────────────────────
void TestVacancyModel::test_filterByText_noMatch()
{
    VacancyFilterModel proxy;
    proxy.setSourceModel(m_model);
    proxy.setTextFilter("xyz_никогда_не_найдёт");
    QCOMPARE(proxy.rowCount(), 0);
}

void TestVacancyModel::test_filterByText_match()
{
    VacancyFilterModel proxy;
    proxy.setSourceModel(m_model);
    proxy.setTextFilter("Qt");
    QCOMPARE(proxy.rowCount(), 1);   // "Qt Engineer"
}

void TestVacancyModel::test_filterByText_caseInsensitive()
{
    VacancyFilterModel proxy;
    proxy.setSourceModel(m_model);
    proxy.setTextFilter("qt engineer");
    QCOMPARE(proxy.rowCount(), 1);
}

void TestVacancyModel::test_filterByStatus_knownStatus()
{
    VacancyFilterModel proxy;
    proxy.setSourceModel(m_model);
    proxy.setStatusFilter(Status::Offer);
    QCOMPARE(proxy.rowCount(), 1);
}

void TestVacancyModel::test_filterByStatus_all()
{
    VacancyFilterModel proxy;
    proxy.setSourceModel(m_model);
    proxy.setStatusFilter("");   // empty = all
    QCOMPARE(proxy.rowCount(), m_model->rowCount());
}

void TestVacancyModel::test_filterCombined_narrowsResult()
{
    VacancyFilterModel proxy;
    proxy.setSourceModel(m_model);
    proxy.setTextFilter("C++");          // matches C++ Dev, Lead C++, C++ Gamedev
    proxy.setStatusFilter(Status::Applied);  // only C++ Dev
    QCOMPARE(proxy.rowCount(), 1);
}

void TestVacancyModel::test_filterReset_restoresRows()
{
    VacancyFilterModel proxy;
    proxy.setSourceModel(m_model);
    proxy.setTextFilter("EPAM");
    QCOMPARE(proxy.rowCount(), 1);
    proxy.setTextFilter("");
    QCOMPARE(proxy.rowCount(), m_model->rowCount());
}

// ── Sort ─────────────────────────────────────────────────────
void TestVacancyModel::test_sort_doesNotCrash()
{
    VacancyFilterModel proxy;
    proxy.setSourceModel(m_model);
    proxy.sort(IVacancyModel::ColDate,    Qt::DescendingOrder);
    proxy.sort(IVacancyModel::ColCompany, Qt::AscendingOrder);
    QCOMPARE(proxy.rowCount(), m_model->rowCount());
}

// ── Flags ─────────────────────────────────────────────────────
void TestVacancyModel::test_flags_editableColumns()
{
    const QList<int> editable = {
        IVacancyModel::ColTitle, IVacancyModel::ColCompany,
        IVacancyModel::ColStatus, IVacancyModel::ColNotes
    };
    for (int c : editable) {
        const Qt::ItemFlags f = m_model->flags(m_model->index(0, c));
        QVERIFY2(f & Qt::ItemIsEditable,
                 qPrintable(QString("Column %1 should be editable").arg(c)));
    }
}

void TestVacancyModel::test_flags_readOnlyColumns()
{
    const QList<int> readOnly = {
        IVacancyModel::ColDate, IVacancyModel::ColSource,
        IVacancyModel::ColSalaryMin, IVacancyModel::ColUrl
    };
    for (int c : readOnly) {
        const Qt::ItemFlags f = m_model->flags(m_model->index(0, c));
        QVERIFY2(!(f & Qt::ItemIsEditable),
                 qPrintable(QString("Column %1 should be read-only").arg(c)));
    }
}

QTEST_MAIN(TestVacancyModel)
#include "test_vacancy_model.moc"
