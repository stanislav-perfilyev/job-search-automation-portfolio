cmake_minimum_required(VERSION 3.16)
project(FileWatcher CXX)
set(CMAKE_CXX_STANDARD 17)

add_executable(file_watcher file_watcher.cpp)

if(MSVC)
    target_compile_options(file_watcher PRIVATE /W4)
    target_compile_definitions(file_watcher PRIVATE UNICODE _UNICODE)
    set_target_properties(file_watcher PROPERTIES LINK_FLAGS "/SUBSYSTEM:CONSOLE")
endif()
