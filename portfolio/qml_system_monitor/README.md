# QML System Monitor — Portfolio Project

Real-time system monitor: CPU load, RAM usage, Uptime with animated gauge bars.  
Demonstrates idiomatic C++ ↔ QML integration using Qt's property binding engine.

**Target roles:** Qt/QML developer, Embedded Linux GUI, Aurora OS

## What it demonstrates

**C++ backend (`SystemStats`):**
- `Q_PROPERTY` with `NOTIFY` signals — QML auto-updates on data change without manual refresh
- `QTimer` at 1-second interval — polling `/proc/stat` and `/proc/meminfo` (Linux) / `GetSystemTimes` + `GlobalMemoryStatusEx` (Windows)
- Delta-based CPU load calculation between two consecutive reads
- Cross-platform conditional compilation (`#ifdef Q_OS_LINUX` / `Q_OS_WIN`)

**QML frontend:**
- `ApplicationWindow` + `ColumnLayout` — declarative layout
- Inline reusable `component GaugeItem` — avoids separate file proliferation
- `Behavior on width { NumberAnimation { easing.type: Easing.OutCubic } }` — smooth 300ms animation
- `required property` — type-safe parameters for the gauge component
- Context property binding: `rootContext()->setContextProperty("systemStats", &stats)`

## Architecture

```
main.cpp
  └── SystemStats (QObject, lives on main thread)
        ├── QTimer (1s) → updateStats()
        │     ├── reads /proc/stat or GetSystemTimes
        │     ├── computes cpuPercent (delta)
        │     └── reads memPercent, uptimeSecs
        └── exposes to QML as "systemStats" context property
              └── main.qml
                    └── GaugeItem { value: systemStats.cpuPercent }
                    └── GaugeItem { value: systemStats.memPercent }
```

## Build

```bash
mkdir build && cd build
cmake .. -DCMAKE_PREFIX_PATH=/path/to/Qt6
cmake --build .
./qml_system_monitor
```

Requires: Qt 6.2+, CMake 3.21+

## Key design decisions

- **No polling in QML** — all timing logic stays in C++; QML only reacts to signals (correct MVC separation)
- **Single QObject** — avoids over-engineering for a monitor with few metrics
- **Reusable GaugeItem** — inline `component` keeps the file count low while enabling DRY layouts
