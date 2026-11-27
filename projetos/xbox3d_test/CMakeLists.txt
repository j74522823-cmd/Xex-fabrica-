cmake_minimum_required(VERSION 3.25)
project(xbox3d_test C)

find_package(Python3 REQUIRED COMPONENTS Interpreter)

set(PLAYER_OBJ_HEADER "${CMAKE_CURRENT_BINARY_DIR}/player_obj.h")
add_custom_command(
    OUTPUT "${PLAYER_OBJ_HEADER}"
    COMMAND "${Python3_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/obj_to_header.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/assets/player_lowpoly.obj"
        "${PLAYER_OBJ_HEADER}"
    DEPENDS
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/obj_to_header.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/assets/player_lowpoly.obj"
    VERBATIM
)
add_custom_target(player_model_asset DEPENDS "${PLAYER_OBJ_HEADER}")

add_executable(xbox3d_test main.c "${PLAYER_OBJ_HEADER}")
add_dependencies(xbox3d_test player_model_asset)
target_include_directories(xbox3d_test PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")

set_target_properties(xbox3d_test PROPERTIES
    C_STANDARD 17
    C_EXTENSIONS ON
)
target_compile_options(xbox3d_test PRIVATE -Wall -Wextra)

xsdk_add_shaders(xbox3d_test house.vert house.frag)
xsdk_add_xex(xbox3d_test NAME "XSDK Two Player House")
