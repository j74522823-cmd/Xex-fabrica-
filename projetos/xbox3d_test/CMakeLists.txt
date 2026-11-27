cmake_minimum_required(VERSION 3.25)
project(xbox3d_test CXX)

add_executable(xbox3d_test
    main.cpp
)

set_target_properties(xbox3d_test PROPERTIES
    CXX_STANDARD 20
    CXX_EXTENSIONS ON
)

target_compile_options(xbox3d_test PRIVATE -Wall -Wextra)

xsdk_add_shaders(xbox3d_test square3d.vert square3d.frag)
xsdk_add_xex(xbox3d_test NAME "XSDK 3D Test")
