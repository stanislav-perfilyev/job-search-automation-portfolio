#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include "SystemStats.h"

int main(int argc, char* argv[]) {
    QGuiApplication app(argc, argv);
    app.setApplicationName("QML System Monitor");
    app.setApplicationVersion("1.0");

    SystemStats stats;

    QQmlApplicationEngine engine;
    // Expose C++ object to QML under the name "systemStats"
    engine.rootContext()->setContextProperty("systemStats", &stats);
    // qt_add_qml_module registers QML files under /qt/qml/{URI}/{relative_path}
    // URI=SystemMonitor, file=qml/main.qml → qrc:/qt/qml/SystemMonitor/qml/main.qml
    engine.load(QUrl(QStringLiteral("qrc:/qt/qml/SystemMonitor/qml/main.qml")));

    if (engine.rootObjects().isEmpty()) return -1;
    return app.exec();
}
