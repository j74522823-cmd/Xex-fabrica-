cmake_minimum_required(VERSION 3.25)
project(xbox3d_test C)

add_executable(xbox3d_test
    main.c
)

set_target_properties(xbox3d_test PROPERTIES
    C_STANDARD 17
    C_EXTENSIONS ON
)

target_compile_options(xbox3d_test PRIVATE -Wall -Wextra)

xsdk_add_shaders(xbox3d_test house.vert house.frag)
xsdk_add_xex(xbox3d_test NAME "XSDK Two Player House")
