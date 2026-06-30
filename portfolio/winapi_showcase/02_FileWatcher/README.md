# File Watcher — WinAPI Showcase #2

Real-time мониторинг файловой системы Windows через ReadDirectoryChangesW с Overlapped I/O.

## Что демонстрирует

- `ReadDirectoryChangesW` — асинхронный мониторинг директории и поддиректорий
- `OVERLAPPED` + `CreateEvent` — non-blocking I/O без блокировки основного потока
- `WaitForSingleObjectEx` — ожидание события с таймаутом
- `GetOverlappedResult` — получение результата асинхронной операции
- `FILE_NOTIFY_INFORMATION` — парсинг структур изменений
- `std::thread` + `std::mutex` + `std::function` — callback-архитектура

## Применение (DLP-контекст)

Аналогичный принцип используется в DLP-системах для перехвата файловых операций
(копирование на USB, отправка по сети, создание архивов).

## Сборка

```
mkdir build && cd build
cmake .. -G "Visual Studio 17 2022"
cmake --build . --config Release

# Мониторить C:\Users:
Release\file_watcher.exe C:\Users
```
