# Portfolio Projects — Станислав Перфильев

Демонстрационные проекты для конкретных вакансий. Каждый проект = доказательство навыка.

## WinAPI Showcase (C++17 + Win32 API)

Целевые вакансии: **ProfiStaff Senior C++ DLP** (400k RUB), DLP-направление в целом.

| Проект | Ключевые API | Что доказывает |
|--------|-------------|----------------|
| [01_ProcessMonitor](winapi_showcase/01_ProcessMonitor/) | EnumProcesses, OpenProcess, GetProcessMemoryInfo, TH32CS | Мониторинг процессов, многопоточность (std::thread/mutex) |
| [02_FileWatcher](winapi_showcase/02_FileWatcher/) | ReadDirectoryChangesW, OVERLAPPED, CreateEvent | Перехват файловых операций (DLP-паттерн) |
| [03_NamedPipeIPC](winapi_showcase/03_NamedPipeIPC/) | CreateNamedPipe, ConnectNamedPipe, ReadFile/WriteFile | IPC агент↔сервер (архитектура DLP-агента) |

## QML System Monitor (C++17 + Qt6 QML)

Целевые вакансии: **Магнит Ведущий C++**, **Открытая МП (Aurora OS)**.

| Что демонстрирует |
|-------------------|
| Q_PROPERTY + NOTIFY → автобиндинг данных в QML |
| QTimer-driven backend, /proc/stat и /proc/meminfo |
| Inline QML component с required property |
| Behavior + NumberAnimation — анимация gauge |
| Кроссплатформенный код (Linux + Windows) |

→ [qml_system_monitor/](qml_system_monitor/)

## D-Bus Service (Qt6 + QtDBus)

Целевые вакансии: **Открытая МП (ОС Аврора)**, вакансии Linux desktop/embedded.

| Что демонстрирует |
|-------------------|
| Регистрация well-known name на session bus |
| Экспорт C++ slots как D-Bus методов |
| QDBusReply<T>, QVariantMap через IPC |
| Периодические D-Bus сигналы (StatsUpdated) |
| QDBusInterface (клиент) — вызов удалённых методов |

→ [dbus_service/](dbus_service/)

## MIL-STD-1553B Protocol Analyzer (Delphi/Pascal)

Целевые вакансии: **МКО Системы**, авиационная и оборонная отрасль.

| Что демонстрирует |
|-------------------|
| Бит-точный декодер протокола МКО (MIL-STD-1553B) |
| State machine: BC/RT/BM режимы |
| DUnit тесты (40+ тест-кейсов) |
| Object Pascal — лаконичный типизированный код |

→ [mil1553_analyzer/](mil1553_analyzer/)
