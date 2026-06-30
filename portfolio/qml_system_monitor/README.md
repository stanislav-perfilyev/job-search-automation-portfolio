# QML System Monitor — Portfolio Project

Real-time системный монитор: CPU, RAM, Uptime с анимированными gauge-барами.
Демонстрирует интеграцию C++ backend ↔ QML frontend.

## Что демонстрирует

**C++ (backend):**
- `Q_PROPERTY` с `NOTIFY` сигналами — автоматическое обновление QML при изменении данных
- `QTimer` — периодический опрос (1 сек)
- Чтение `/proc/stat` и `/proc/meminfo` (Linux) / `GetSystemTimes` + `GlobalMemoryStatusEx` (Windows)
- Delta-расчёт CPU load между двумя замерами

**QML (frontend):**
- `ApplicationWindow` + `ColumnLayout`
- Inline `component` для переиспользуемого gauge
- `Behavior on width` — плавная анимация (NumberAnimation + Easing)
- `required property` — типобезопасные параметры компонента
- Биндинг на C++ объект через `rootContext()->setContextProperty`

## Сборка

```bash
mkdir build && cd build
cmake .. -DCMAKE_PREFIX_PATH=/path/to/Qt6
cmake --build .
./qml_system_monitor
```

## Архитектура

```
main.cpp
  └── создаёт SystemStats (C++ объект)
  └── передаёт в QML движок как "systemStats"
      └── main.qml биндится на systemStats.cpuPercent, .memPercent и т.д.
          └── GaugeItem component — анимированный progress bar
```
