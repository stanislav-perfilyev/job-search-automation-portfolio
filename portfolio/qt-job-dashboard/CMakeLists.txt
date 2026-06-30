cmake_minimum_required(VERSION 3.20)
project(JobSearchDashboard VERSION 1.2.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

find_package(Qt6 REQUIRED COMPONENTS Core Widgets Sql Charts)

set(SOURCES
    src/main.cpp
    src/mainwindow/mainwindow.cpp
    src/models/vacancysqlmodel.cpp
    src/models/vacancyfiltermodel.cpp
    src/views/vacancyview.cpp
    src/views/statisticsview.cpp
    src/widgets/kpiwidget.cpp
    src/widgets/statusdelegate.cpp
    src/widgets/processrunner.cpp
    src/dialogs/vacancydetaildialog.cpp
    src/dialogs/settingsdialog.cpp
    src/dialogs/scriptdialog.cpp
    src/dialogs/diagnosticsdialog.cpp
    src/utils/csvexporter.cpp
    src/utils/logging.cpp
)

set(HEADERS
    src/mainwindow/mainwindow.h
    src/models/ivacancymodel.h
    src/models/vacancysqlmodel.h
    src/models/vacancyfiltermodel.h
    src/views/vacancyview.h
    src/views/statisticsview.h
    src/widgets/kpiwidget.h
    src/widgets/statusdelegate.h
    src/widgets/processrunner.h
    src/dialogs/vacancydetaildialog.h
    src/dialogs/settingsdialog.h
    src/dialogs/scriptdialog.h
    src/dialogs/diagnosticsdialog.h
    src/utils/csvexporter.h
    src/utils/dberror.h
    src/utils/status.h
    src/utils/logging.h
)

set(RESOURCES
    assets/resources.qrc
)

add_executable(${PROJECT_NAME} ${SOURCES} ${HEADERS} ${RESOURCES})
target_include_directories(${PROJECT_NAME} PRIVATE src)
target_link_libraries(${PROJECT_NAME} PRIVATE
    Qt6::Core Qt6::Widgets Qt6::Sql Qt6::Charts)
target_compile_options(${PROJECT_NAME} PRIVATE
    $<$<CXX_COMPILER_ID:GNU,Clang>:-Wall -Wextra -Wpedantic>
    $<$<CXX_COMPILER_ID:MSVC>:/W4 /utf-8>)

option(BUILD_TESTS "Build unit tests" ON)
if(BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()
