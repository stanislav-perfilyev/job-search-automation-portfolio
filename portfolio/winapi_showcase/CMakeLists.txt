cmake_minimum_required(VERSION 3.16)
project(WinApiShowcase CXX)

# This showcase exercises real Win32 APIs (windows.h, psapi, tlhelp32,
# named pipes) directly, with no cross-platform abstraction layer — it is
# only buildable on Windows (MSVC or MinGW-w64). Configuring on Linux/WSL
# is expected to stop here rather than fail deep inside a subdirectory.
if(NOT WIN32)
    message(WARNING
        "winapi_showcase targets the native Win32 API and cannot be built "
        "on this platform. Skipping — build on Windows (see CI: windows-latest).")
    return()
endif()

add_subdirectory(01_ProcessMonitor)
add_subdirectory(02_FileWatcher)
add_subdirectory(03_NamedPipeIPC)

enable_testing()
add_subdirectory(tests)
