# D-Bus Service — Portfolio Project

Qt D-Bus сервис и клиент: демонстрация межпроцессного взаимодействия через session bus.
Целевая аудитория: вакансии с Aurora OS / ОС Аврора, Linux desktop, embedded Linux.

## Что демонстрирует

**Сервис:**
- `QDBusConnection::sessionBus()` — подключение к session bus
- `registerService` — регистрация well-known name (`ru.perfilyev.SystemInfo`)
- `registerObject` — экспорт C++ объекта как D-Bus object path
- `Q_CLASSINFO("D-Bus Interface", ...)` — объявление интерфейса
- `ExportAllSlots` / `ExportAllSignals` — автоэкспорт методов и сигналов
- Периодический D-Bus сигнал `StatsUpdated` через `QTimer`

**Клиент:**
- `QDBusInterface` — proxy-объект для удалённого вызова методов
- `QDBusReply<T>` — типобезопасный результат вызова
- `QVariantMap` через D-Bus — передача сложных типов (словарь)

## Архитектура

```
Session D-Bus
    └── ru.perfilyev.SystemInfo  (well-known name)
        └── /ru/perfilyev/SystemInfo  (object path)
            └── ru.perfilyev.SystemInfo  (interface)
                ├── GetHostname() → String
                ├── GetMemoryInfo() → Map<String, Variant>
                ├── GetCpuCount() → Int32
                ├── GetUptime() → String
                ├── Echo(String) → String
                └── Signal: StatsUpdated(String)
```

## Сборка и запуск (Linux)

```bash
mkdir build && cd build
cmake ..
cmake --build .

# Терминал 1 — запустить сервис:
./dbus_service

# Терминал 2 — клиент:
./dbus_client

# Или проверить через dbus-send:
dbus-send --session --print-reply \
  --dest=ru.perfilyev.SystemInfo \
  /ru/perfilyev/SystemInfo \
  ru.perfilyev.SystemInfo.GetHostname
```

## Применение (Aurora OS)

Aurora OS (ОС Аврора) использует D-Bus как основной IPC-механизм.
Паттерн service/client через session bus — стандартный для Aurora приложений.
