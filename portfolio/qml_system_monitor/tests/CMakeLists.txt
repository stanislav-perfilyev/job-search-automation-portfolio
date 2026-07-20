# Included via add_subdirectory() from the top-level CMakeLists.txt —
# inherits CMAKE_CXX_STANDARD and CMAKE_AUTOMOC. Qt6::Test isn't pulled in
# by the qt_add_executable() Quick/Qml setup above, so it's found here.
find_package(Qt6 REQUIRED COMPONENTS Core Test)

add_executable(test_system_stats
    test_system_stats.cpp
    ../src/SystemStats.cpp
)
target_include_directories(test_system_stats PRIVATE ../src)
target_link_libraries(test_system_stats PRIVATE
    Qt6::Core
    Qt6::Test
)
target_compile_options(test_system_stats PRIVATE ${WARNING_FLAGS})
if(WIN32)
    target_link_libraries(test_system_stats PRIVATE psapi)
endif()

add_test(NAME SystemStatsTests COMMAND test_system_stats)
