#include <QCoreApplication>
#include <QDBusInterface>
#include <QDBusReply>
#include <QVariantMap>
#include <QDebug>

static const char SERVICE_NAME[] = "ru.perfilyev.SystemInfo";
static const char OBJECT_PATH[]  = "/ru/perfilyev/SystemInfo";
static const char INTERFACE[]    = "ru.perfilyev.SystemInfo";

int main(int argc, char* argv[]) {
    QCoreApplication app(argc, argv);

    QDBusInterface iface(SERVICE_NAME, OBJECT_PATH, INTERFACE,
                         QDBusConnection::sessionBus());

    if (!iface.isValid()) {
        qCritical() << "Cannot connect to service:" << iface.lastError().message();
        qCritical() << "Is the server running? Start: ./dbus_service";
        return 1;
    }

    // Call methods
    QDBusReply<QString> hostname = iface.call("GetHostname");
    qInfo() << "Hostname:" << hostname.value();

    QDBusReply<int> cpus = iface.call("GetCpuCount");
    qInfo() << "CPU cores:" << cpus.value();

    QDBusReply<QString> uptime = iface.call("GetUptime");
    qInfo() << "Uptime:" << uptime.value();

    QDBusReply<QVariantMap> mem = iface.call("GetMemoryInfo");
    auto memMap = mem.value();
    qInfo() << "Memory: used" << memMap["used_mb"].toInt()
            << "MB / total" << memMap["total_mb"].toInt() << "MB";

    QDBusReply<QString> echo = iface.call("Echo", "Hello from client!");
    qInfo() << "Echo:" << echo.value();

    return 0;
}
