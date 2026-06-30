cmake_minimum_required(VERSION 3.16)
project(WinApiShowcaseTests CXX)
set(CMAKE_CXX_STANDARD 17)

# --- GoogleTest via FetchContent ---
include(FetchContent)
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG        v1.14.0
)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

enable_testing()

# ─── ProcessMonitor tests ────────────────────────────────────────────────────
# Uses StubEnumerator — zero real WinAPI calls, runs on any platform
add_executable(test_process_monitor
    test_process_monitor.cpp
    ../01_ProcessMonitor/ProcessMonitor.cpp
)
target_include_directories(test_process_monitor PRIVATE
    ../01_ProcessMonitor
    ../common
)
target_link_libraries(test_process_monitor PRIVATE
    GTest::gtest
    psapi
)
if(MSVC)
    target_compile_definitions(test_process_monitor PRIVATE UNICODE _UNICODE)
    target_compile_options(test_process_monitor PRIVATE /W4 /WX)
endif()
add_test(NAME ProcessMonitorTests COMMAND test_process_monitor)

# ─── FileWatcher tests ───────────────────────────────────────────────────────
# Tests ActionToString + FileEvent struct; no real I/O in unit tests
add_executable(test_file_watcher
    test_file_watcher.cpp
)
target_include_directories(test_file_watcher PRIVATE
    ../02_FileWatcher
    ../common
)
target_link_libraries(test_file_watcher PRIVATE GTest::gtest)
if(MSVC)
    target_compile_definitions(test_file_watcher PRIVATE UNICODE _UNICODE)
    target_compile_options(test_file_watcher PRIVATE /W4 /WX)
endif()
add_test(NAME FileWatcherTests COMMAND test_file_watcher)

# ─── NamedPipeIPC tests ──────────────────────────────────────────────────────
# Tests protocol constants + echo reply format
add_executable(test_named_pipe
    test_named_pipe.cpp
)
target_include_directories(test_named_pipe PRIVATE
    ../03_NamedPipeIPC
    ../common
)
target_link_libraries(test_named_pipe PRIVATE GTest::gtest)
if(MSVC)
    target_compile_definitions(test_named_pipe PRIVATE UNICODE _UNICODE)
    target_compile_options(test_named_pipe PRIVATE /W4 /WX)
endif()
add_test(NAME NamedPipeTests COMMAND test_named_pipe)
