#pragma once
#include <QLoggingCategory>

// Structured logging categories.
// Usage: qCDebug(lcDb) << "Connected";
// Enable all: export QT_LOGGING_RULES="dashboard.*=true"
Q_DECLARE_LOGGING_CATEGORY(lcDb)      // database
Q_DECLARE_LOGGING_CATEGORY(lcUi)      // ui events
Q_DECLARE_LOGGING_CATEGORY(lcProc)    // QProcess runner
Q_DECLARE_LOGGING_CATEGORY(lcExport)  // CSV / file export
