# Process Monitor — WinAPI Showcase #1

Многопоточный мониторинг процессов Windows с использованием нативного WinAPI.

## Что демонстрирует

- `EnumProcesses` — список PID всех процессов
- `OpenProcess` — handle с PROCESS_QUERY_INFORMATION
- `GetProcessMemoryInfo` — Working Set памяти
- `CreateToolhelp32Snapshot` — снапшот процессов и потоков
- `Process32First/Next` — имена процессов
- `Thread32First/Next` — подсчёт потоков
- `std::thread` + `std::mutex` + `std::atomic<bool>` — многопоточный фон

## Сборка (Windows, MSVC)

```
mkdir build && cd build
cmake .. -G "Visual Studio 17 2022"
cmake --build . --config Release
Release\process_monitor.exe
```
