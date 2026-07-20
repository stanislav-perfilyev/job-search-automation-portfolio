# Included via add_subdirectory() from the top-level CMakeLists.txt —
# inherits CMAKE_CXX_STANDARD, CMAKE_AUTOMOC, and QT_VERSION_MAJOR.
find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)

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
target_compile_options(test_dbus_service PRIVATE ${WARNING_FLAGS})

add_test(NAME DbusServiceTests COMMAND test_dbus_service)
