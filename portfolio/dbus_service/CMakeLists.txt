cmake_minimum_required(VERSION 3.16)
project(DbusShowcase VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 COMPONENTS Core DBus QUIET)
if(NOT Qt6_FOUND)
    find_package(Qt5 REQUIRED COMPONENTS Core DBus)
    set(QT_VERSION_MAJOR 5)
else()
    set(QT_VERSION_MAJOR 6)
endif()

set(WARNING_FLAGS
    $<$<CXX_COMPILER_ID:GNU,Clang>:-Wall -Wextra -Werror>
    $<$<CXX_COMPILER_ID:MSVC>:/W4 /WX>
)

# Service
add_executable(dbus_service
    service/main.cpp
    service/SystemInfoService.cpp
    service/SystemInfoService.h
)
target_link_libraries(dbus_service PRIVATE
    Qt${QT_VERSION_MAJOR}::Core
    Qt${QT_VERSION_MAJOR}::DBus
)
target_compile_options(dbus_service PRIVATE ${WARNING_FLAGS})

# Client
add_executable(dbus_client
    client/main.cpp
)
target_link_libraries(dbus_client PRIVATE
    Qt${QT_VERSION_MAJOR}::Core
    Qt${QT_VERSION_MAJOR}::DBus
)
target_compile_options(dbus_client PRIVATE ${WARNING_FLAGS})

enable_testing()
add_subdirectory(tests)
