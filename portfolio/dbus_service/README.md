# D-Bus Service — Portfolio Project

Qt D-Bus service + client: inter-process communication over the session bus.  
Demonstrates the exact IPC pattern used in Aurora OS (ОС Аврора) applications and Linux desktop middleware.

**Target roles:** Aurora OS developer, Linux embedded, Qt IPC

## What it demonstrates

**Service side:**
- `QDBusConnection::sessionBus()` — connecting to the session bus
- `registerService("ru.perfilyev.SystemInfo")` — claiming a well-known name
- `registerObject("/ru/perfilyev/SystemInfo", ...)` — exporting a C++ object as a D-Bus path
- `Q_CLASSINFO("D-Bus Interface", "ru.perfilyev.SystemInfo")` — interface declaration in class metadata
- `ExportAllSlots` / `ExportAllSignals` — auto-export of public slots and signals
- `QTimer` → periodic `StatsUpdated(QString)` signal broadcast to all listeners

**Client side:**
- `QDBusInterface` — proxy object for calling remote methods
- `QDBusReply<T>` — type-safe return values
- `QVariantMap` over D-Bus — passing structured data (dictionary type `a{sv}`)
- Error handling via `QDBusReply::isValid()`

## D-Bus Interface

```
Session Bus
  └── ru.perfilyev.SystemInfo      (well-known name)
      └── /ru/perfilyev/SystemInfo  (object path)
          └── ru.perfilyev.SystemInfo  (interface)
              ├── GetHostname()  → String
              ├── GetMemoryInfo() → Map<String, Variant>
              ├── GetCpuCount()  → Int32
              ├── GetUptime()    → String
              ├── Echo(String)   → String
              └── Signal: StatsUpdated(String)
```

## Architecture

`service/` hosts `SystemInfoService` (QObject + QDBusContext), registered on the
session bus and exporting its public slots as D-Bus methods. `client/` is a
thin `QDBusInterface` proxy that calls those methods and prints the results.
`tests/` exercises the service's logic directly (no live D-Bus bus needed).

## Usage

Start the service in one terminal, then run the client (or `dbus-send`) in
another — see [Build and run](#build-and-run-linux) below for exact commands.

## Build and run (Linux)

```bash
mkdir build && cd build
cmake ..
cmake --build .

# Terminal 1 — start service:
./dbus_service

# Terminal 2 — client:
./dbus_client

# Or verify via dbus-send:
dbus-send --session --print-reply \
  --dest=ru.perfilyev.SystemInfo \
  /ru/perfilyev/SystemInfo \
  ru.perfilyev.SystemInfo.GetHostname
```

Requires: Qt 6.x with D-Bus support, `dbus-daemon` running on session bus

## Aurora OS relevance

Aurora OS (ОС Аврора, built on Sailfish OS) uses D-Bus as its primary IPC mechanism between UI applications, middleware daemons, and hardware abstraction layers. The service/client pattern with `registerService` + `registerObject` is the standard way to expose system APIs to Aurora apps — making this pattern directly applicable to production Aurora development.

## Key design decisions

- **Well-known name** follows reverse-domain convention — matches Aurora OS naming requirements
- **`QVariantMap` return type** — avoids custom D-Bus type registration while keeping the API flexible
- **Signal broadcast** — demonstrates publisher/subscriber pattern over D-Bus without explicit subscriber list
