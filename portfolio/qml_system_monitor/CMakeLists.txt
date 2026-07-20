cmake_minimum_required(VERSION 3.16)
project(QmlSystemMonitor VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)

# qt_add_executable / qt_add_qml_module are Qt 6 CMake API — Qt 5 not supported
find_package(Qt6 REQUIRED COMPONENTS Core Gui Qml Quick)

set(WARNING_FLAGS
    $<$<CXX_COMPILER_ID:GNU,Clang>:-Wall -Wextra -Werror>
    $<$<CXX_COMPILER_ID:MSVC>:/W4 /WX>
)

qt_add_executable(qml_system_monitor
    src/main.cpp
    src/SystemStats.cpp
    src/SystemStats.h
)

qt_add_qml_module(qml_system_monitor
    URI SystemMonitor
    VERSION 1.0
    QML_FILES
        qml/main.qml
)

target_link_libraries(qml_system_monitor PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Qml
    Qt6::Quick
)
target_compile_options(qml_system_monitor PRIVATE ${WARNING_FLAGS})

if(WIN32)
    target_link_libraries(qml_system_monitor PRIVATE psapi)
endif()

enable_testing()
add_subdirectory(tests)
