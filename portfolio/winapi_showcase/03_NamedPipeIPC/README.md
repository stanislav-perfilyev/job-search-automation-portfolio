# Named Pipe IPC — WinAPI Showcase #3

Inter-process communication через именованные каналы Windows.
Многоклиентный сервер с потоком на каждое подключение.

## Что демонстрирует

- `CreateNamedPipe` — создание именованного канала (серверная сторона)
- `ConnectNamedPipe` — блокирующий accept нового клиента
- `WaitNamedPipeW` — ожидание доступности канала (клиент)
- `CreateFile` — подключение клиента к pipe
- `SetNamedPipeHandleState` — переключение в режим сообщений
- `ReadFile` / `WriteFile` — дуплексный обмен данными
- `std::thread` (detach) — один поток на клиента
- `std::mutex` — синхронизация вывода

## Применение (DLP-контекст)

Named Pipes — стандартный IPC механизм DLP-агентов (userspace ↔ kernel driver,
агент ↔ сервер политик). Этот же паттерн используется в Windows Security Center API.

## Сборка и запуск

```
mkdir build && cd build
cmake .. -G "Visual Studio 17 2022"
cmake --build . --config Release

# Терминал 1:
Release\pipe_server.exe

# Терминал 2 (можно запустить несколько):
Release\pipe_client.exe
```
