cmake_minimum_required(VERSION 3.16)
project(DbusShowcase VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 COMPONENTS Core DBus QUIET)
if(NOT Qt6_FOUND)
    find_package(Qt5 REQUIRED COMPONENTS Core DBus)
    set(QT_VERSION_MAJOR 5)
else()
    set(QT_VERSION_MAJOR 6)
endif()

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

# Client
add_executable(dbus_client
    client/main.cpp
)
target_link_libraries(dbus_client PRIVATE
    Qt${QT_VERSION_MAJOR}::Core
    Qt${QT_VERSION_MAJOR}::DBus
)
