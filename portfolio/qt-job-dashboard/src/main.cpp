#include "mainwindow/mainwindow.h"
#include <QApplication>
#include <QSqlDatabase>

int main(int argc, char* argv[])
{
    QApplication app(argc, argv);
    app.setApplicationName("JobSearchDashboard");
    app.setOrganizationName("StasPerfiliev");
    app.setApplicationVersion("1.0.0");

    // PostgreSQL driver must be available
    if (!QSqlDatabase::isDriverAvailable("QPSQL")) {
        qFatal("Qt SQL QPSQL driver not available. Install libqt6sql-psql.");
    }

    MainWindow w;
    w.show();
    return app.exec();
}
