cmake_minimum_required(VERSION 3.16)
project(DbusServiceTests CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 COMPONENTS Core DBus Test QUIET)
if(NOT Qt6_FOUND)
    find_package(Qt5 REQUIRED COMPONENTS Core DBus Test)
    set(QT_VERSION_MAJOR 5)
else()
    set(QT_VERSION_MAJOR 6)
endif()

enable_testing()

add_executable(test_dbus_service
    test_dbus_service.cpp
    ../service/SystemInfoService.cpp
)
target_include_directories(test_dbus_service PRIVATE ../service)
target_link_libraries(test_dbus_service PRIVATE
    Qt${QT_VERSION_MAJOR}::Core
    Qt${QT_VERSION_MAJOR}::DBus
    Qt${QT_VERSION_MAJOR}::Test
)

add_test(NAME DbusServiceTests COMMAND test_dbus_service)
