#include "csvexporter.h"
#include "logging.h"
#include <QAbstractItemModel>
#include <QFile>
#include <QFileDialog>
#include <QTextStream>
#include <QMessageBox>
#include <QWidget>
#include <QDateTime>

bool CsvExporter::exportModel(QAbstractItemModel* model,
                              const QString& filePath,
                              QWidget* parent)
{
    if (!model) {
        qCWarning(lcExport) << "exportModel called with null model";
        return false;
    }

    QString path = filePath;
    if (path.isEmpty()) {
        const QString defaultName =
            QString("vacancies_%1.csv")
                .arg(QDateTime::currentDateTime().toString("yyyyMMdd_HHmm"));
        path = QFileDialog::getSaveFileName(
            parent, "Экспорт в CSV", defaultName,
            "CSV files (*.csv);;All files (*)");
        if (path.isEmpty()) return false;  // user cancelled
    }

    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Text)) {
        const QString msg = QString("Cannot open file: %1").arg(path);
        qCWarning(lcExport) << msg;
        QMessageBox::critical(parent, "Ошибка экспорта",
            QString("Не удалось открыть файл:\n%1").arg(path));
        return false;
    }

    QTextStream out(&file);
    out.setEncoding(QStringConverter::Utf8);
    out << "\xEF\xBB\xBF";   // UTF-8 BOM

    const int cols = model->columnCount();
    const int rows = model->rowCount();

    // Header row
    QStringList header;
    header.reserve(cols);
    for (int c = 0; c < cols; ++c)
        header << escaped(model->headerData(c, Qt::Horizontal).toString());
    out << header.join(",") << "\n";

    // Data rows
    for (int r = 0; r < rows; ++r) {
        QStringList row;
        row.reserve(cols);
        for (int c = 0; c < cols; ++c)
            row << escaped(model->data(model->index(r, c)).toString());
        out << row.join(",") << "\n";
    }

    qCInfo(lcExport) << "Exported" << rows << "rows to" << path;
    return true;
}

QString CsvExporter::escaped(const QString& value)
{
    // RFC 4180: field must be quoted if it contains comma, quote, or newline.
    if (value.contains(',') || value.contains('"') || value.contains('\n')) {
        QString quoted = value;
        quoted.replace('"', "\"\"");   // escape embedded quotes
        return '"' + quoted + '"';
    }
    return value;
}
