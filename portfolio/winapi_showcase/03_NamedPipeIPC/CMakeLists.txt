cmake_minimum_required(VERSION 3.16)
project(NamedPipeIPC CXX)
set(CMAKE_CXX_STANDARD 17)

add_executable(pipe_server pipe_server.cpp)
add_executable(pipe_client pipe_client.cpp)

if(MSVC)
    foreach(tgt pipe_server pipe_client)
        target_compile_options(${tgt} PRIVATE /W4)
        target_compile_definitions(${tgt} PRIVATE UNICODE _UNICODE)
    endforeach()
endif()
