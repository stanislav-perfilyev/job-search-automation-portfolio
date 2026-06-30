#include <QtTest/QtTest>
#include <QStandardItemModel>
#include <QTemporaryFile>
#include <QFile>
#include <QTextStream>
#include "utils/csvexporter.h"

class TestCsvExporter : public QObject {
    Q_OBJECT
private slots:
    void test_emptyModel();
    void test_headerOnly();
    void test_basicExport();
    void test_quotingCommas();
    void test_quotingQuotes();
    void test_quotingNewlines();
    void test_utf8Bom();
};

static QStandardItemModel* makeModel(
    const QStringList& headers,
    const QVector<QStringList>& rows,
    QObject* parent = nullptr)
{
    auto* m = new QStandardItemModel(parent);
    m->setColumnCount(headers.size());
    for (int c = 0; c < headers.size(); ++c)
        m->setHeaderData(c, Qt::Horizontal, headers[c]);
    for (const auto& row : rows) {
        QList<QStandardItem*> items;
        for (const auto& cell : row)
            items << new QStandardItem(cell);
        m->appendRow(items);
    }
    return m;
}

static QString readFile(const QString& path)
{
    QFile f(path);
    f.open(QIODevice::ReadOnly | QIODevice::Text);
    QTextStream s(&f);
    s.setEncoding(QStringConverter::Utf8);
    return s.readAll();
}

void TestCsvExporter::test_emptyModel()
{
    QTemporaryFile tmp; tmp.open();
    auto* m = makeModel({}, {}, this);
    QVERIFY(CsvExporter::exportModel(m, tmp.fileName()));
}

void TestCsvExporter::test_headerOnly()
{
    QTemporaryFile tmp; tmp.open();
    auto* m = makeModel({"Дата","Компания","Статус"}, {}, this);
    QVERIFY(CsvExporter::exportModel(m, tmp.fileName()));
    const QString content = readFile(tmp.fileName());
    QVERIFY(content.contains("Дата"));
    QVERIFY(content.contains("Компания"));
    QVERIFY(content.contains("Статус"));
}

void TestCsvExporter::test_basicExport()
{
    QTemporaryFile tmp; tmp.open();
    auto* m = makeModel({"A","B"}, {{"v1","v2"},{"v3","v4"}}, this);
    QVERIFY(CsvExporter::exportModel(m, tmp.fileName()));
    const QString c = readFile(tmp.fileName());
    QVERIFY(c.contains("v1"));
    QVERIFY(c.contains("v4"));
    QCOMPARE(c.count('\n'), 3);  // header + 2 rows
}

void TestCsvExporter::test_quotingCommas()
{
    QTemporaryFile tmp; tmp.open();
    auto* m = makeModel({"A"}, {{"hello, world"}}, this);
    QVERIFY(CsvExporter::exportModel(m, tmp.fileName()));
    const QString c = readFile(tmp.fileName());
    QVERIFY(c.contains("\"hello, world\""));
}

void TestCsvExporter::test_quotingQuotes()
{
    QTemporaryFile tmp; tmp.open();
    auto* m = makeModel({"A"}, {{"say \"hi\""}}, this);
    QVERIFY(CsvExporter::exportModel(m, tmp.fileName()));
    const QString c = readFile(tmp.fileName());
    QVERIFY(c.contains("\"say \"\"hi\"\"\""));
}

void TestCsvExporter::test_quotingNewlines()
{
    QTemporaryFile tmp; tmp.open();
    auto* m = makeModel({"A"}, {{"line1\nline2"}}, this);
    QVERIFY(CsvExporter::exportModel(m, tmp.fileName()));
    const QString c = readFile(tmp.fileName());
    QVERIFY(c.contains('"'));  // must be quoted
}

void TestCsvExporter::test_utf8Bom()
{
    QTemporaryFile tmp; tmp.open();
    auto* m = makeModel({"A"}, {{"тест"}}, this);
    QVERIFY(CsvExporter::exportModel(m, tmp.fileName()));
    QFile f(tmp.fileName());
    f.open(QIODevice::ReadOnly);
    const QByteArray bytes = f.read(3);
    // UTF-8 BOM = EF BB BF
    QCOMPARE(static_cast<unsigned char>(bytes[0]), 0xEF);
    QCOMPARE(static_cast<unsigned char>(bytes[1]), 0xBB);
    QCOMPARE(static_cast<unsigned char>(bytes[2]), 0xBF);
}

QTEST_MAIN(TestCsvExporter)
#include "test_csv_exporter.moc"
