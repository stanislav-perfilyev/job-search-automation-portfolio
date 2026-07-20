#include <QCoreApplication>
#include <QDBusConnection>
#include <QDebug>
#include "SystemInfoService.h"

static const char SERVICE_NAME[] = "ru.perfilyev.SystemInfo";
static const char OBJECT_PATH[]  = "/ru/perfilyev/SystemInfo";

int main(int argc, char* argv[]) {
    QCoreApplication app(argc, argv);

    auto bus = QDBusConnection::sessionBus();
    if (!bus.isConnected()) {
        qCritical() << "Cannot connect to D-Bus session bus.";
        return 1;
    }

    if (!bus.registerService(SERVICE_NAME)) {
        qCritical() << "Failed to register service:" << bus.lastError().message();
        return 1;
    }

    SystemInfoService service;
    if (!bus.registerObject(OBJECT_PATH, &service,
                            QDBusConnection::ExportAllSlots |
                            QDBusConnection::ExportAllSignals)) {
        qCritical() << "Failed to register object:" << bus.lastError().message();
        return 1;
    }

    qInfo() << "Service registered on session bus as" << SERVICE_NAME;
    qInfo() << "Object path:" << OBJECT_PATH;
    qInfo() << "Waiting for calls...";

    return app.exec();
}
