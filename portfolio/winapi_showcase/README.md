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

The repo root now has a single top-level `CMakeLists.txt` that builds all
three subprojects and the test suite in one pass (it `return()`s early on
non-Windows configures, since every target links against real Win32 APIs):

```bash
mkdir build && cd build
cmake .. -G "Visual Studio 17 2022"
cmake --build . --config Release
ctest -C Release --output-on-failure
```

Each subproject also still builds standalone (`cd 01_ProcessMonitor && cmake -B build ...`) if you only want one binary.

## Usage

```bash
# Process Monitor — live top-20 by working set, refreshes on Enter
01_ProcessMonitor\process_monitor.exe

# File Watcher — watches a directory (default: current dir) for changes
02_FileWatcher\file_watcher.exe C:\path\to\watch

# Named Pipe IPC — run the server, then one or more clients in separate terminals
03_NamedPipeIPC\pipe_server.exe
03_NamedPipeIPC\pipe_client.exe
```

## Architecture

Each subproject follows the same shape: a small WinAPI-facing class (or free
functions) that owns OS handles via the shared `winapi::Handle` RAII wrapper
in `common/`, a background `std::thread` for the blocking/polling WinAPI
call, and a thin `main()`/`wmain()` that wires the class to console I/O.
Console output from background threads is always assembled into a single
`std::wstring` (via `std::wostringstream` or a mutex-guarded `Log()` helper)
before one final `<<` to `wcout`/`wcerr`, so output from concurrent threads
never interleaves mid-line. `01_ProcessMonitor`'s core logic is split behind
`IProcessEnumerator` specifically so `tests/` can exercise it with a stub
enumerator, with zero real WinAPI calls in the test binary.

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
