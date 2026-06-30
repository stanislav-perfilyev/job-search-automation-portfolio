cmake_minimum_required(VERSION 3.16)
project(QmlSystemMonitorTests CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 COMPONENTS Core Test QUIET)
if(NOT Qt6_FOUND)
    find_package(Qt5 REQUIRED COMPONENTS Core Test)
    set(QT_VERSION_MAJOR 5)
else()
    set(QT_VERSION_MAJOR 6)
endif()

enable_testing()

add_executable(test_system_stats
    test_system_stats.cpp
    ../src/SystemStats.cpp
)
target_include_directories(test_system_stats PRIVATE ../src)
target_link_libraries(test_system_stats PRIVATE
    Qt${QT_VERSION_MAJOR}::Core
    Qt${QT_VERSION_MAJOR}::Test
)
if(WIN32)
    target_link_libraries(test_system_stats PRIVATE psapi)
endif()

add_test(NAME SystemStatsTests COMMAND test_system_stats)
