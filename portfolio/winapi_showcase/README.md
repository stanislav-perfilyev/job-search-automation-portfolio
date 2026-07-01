# WinAPI Showcase — C++ Portfolio

Three production-quality Windows API programs targeting DLP / endpoint security domain.  
Each project demonstrates a distinct low-level Windows subsystem with modern C++17 idioms.

| # | Project | WinAPI Subsystem | Lines |
|---|---------|-----------------|-------|
| 1 | [Process Monitor](01_ProcessMonitor/) | `ToolHelp32` · `PSAPI` · threads | ~200 |
| 2 | [File Watcher](02_FileWatcher/) | `ReadDirectoryChangesW` · Overlapped I/O | ~150 |
| 3 | [Named Pipe IPC](03_NamedPipeIPC/) | Named Pipes · multi-client server | ~200 |

## Why these projects?

These three subsystems appear repeatedly in DLP agent architecture (e.g., Endpoint Protector, ProfiStaff, SearchInform):

- **Process enumeration** — policy enforcement: which process may write where
- **File-system monitoring** — intercept copy/archive/send operations in real time
- **Pipe IPC** — userspace agent ↔ kernel driver, agent ↔ policy server communication

## Key C++ techniques demonstrated

- `std::thread` + `std::mutex` + `std::atomic<bool>` — background monitoring loops
- RAII handle wrappers — no raw `CloseHandle` / `CloseHandle` in destructors
- Overlapped (async) I/O — non-blocking file-system events
- Callback architecture via `std::function` — decoupled event handling
- Google Test unit tests (`tests/`) — mock-based testing of core logic

## Build (Windows, MSVC / Visual Studio 2022)

```bash
# Build all three projects
cd 01_ProcessMonitor && mkdir build && cd build
cmake .. -G "Visual Studio 17 2022" && cmake --build . --config Release

cd ../../02_FileWatcher && mkdir build && cd build
cmake .. -G "Visual Studio 17 2022" && cmake --build . --config Release

cd ../../03_NamedPipeIPC && mkdir build && cd build
cmake .. -G "Visual Studio 17 2022" && cmake --build . --config Release
```

## Project structure

```
winapi_showcase/
├── 01_ProcessMonitor/     # EnumProcesses + ToolHelp32 + multi-thread
│   ├── ProcessMonitor.cpp
│   ├── ProcessInfo.h
│   └── README.md
├── 02_FileWatcher/        # ReadDirectoryChangesW + OVERLAPPED
│   ├── file_watcher.cpp
│   └── README.md
├── 03_NamedPipeIPC/       # CreateNamedPipe server + multi-client
│   ├── pipe_server.cpp
│   ├── pipe_client.cpp
│   └── README.md
├── common/                # Shared RAII handles, logging utils
└── tests/                 # Google Test suite
```

## Domain context

These projects were built to demonstrate hands-on experience with the exact WinAPI surface used in DLP products — which is often the gating question in interviews for endpoint security / system programming roles.
