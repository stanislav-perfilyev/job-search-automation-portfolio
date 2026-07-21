cmake_minimum_required(VERSION 3.16)
project(ProcessMonitor CXX)
set(CMAKE_CXX_STANDARD 17)

add_executable(process_monitor
    process_monitor.cpp
    ProcessMonitor.cpp
)
target_include_directories(process_monitor PRIVATE . ../common)
target_link_libraries(process_monitor PRIVATE psapi)

target_compile_definitions(process_monitor PRIVATE UNICODE _UNICODE)
if(MSVC)
    target_compile_options(process_monitor PRIVATE /W4 /WX)
else()
    target_compile_options(process_monitor PRIVATE -Wall -Wextra -Werror)
endif()
