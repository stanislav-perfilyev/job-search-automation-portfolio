#pragma once
#include <QString>

class QAbstractItemModel;
class QWidget;   // forward declaration (was missing)

// Exports any QAbstractItemModel to a UTF-8 CSV file (RFC 4180).
// BOM prefix ensures correct encoding detection in Excel/LibreOffice.
class CsvExporter {
public:
    // Returns true on success. Opens QFileDialog if filePath is empty.
    // Thread: must be called from UI thread (opens dialogs).
    [[nodiscard]] static bool exportModel(QAbstractItemModel* model,
                                          const QString& filePath = {},
                                          QWidget* parent = nullptr);

private:
    [[nodiscard]] static QString escaped(const QString& value);
};
