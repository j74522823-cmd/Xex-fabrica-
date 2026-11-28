cmake_minimum_required(VERSION 3.20)
project(re4coop C)

# Configure com:
#   cmake -B build-xbox -G Ninja -DCMAKE_TOOLCHAIN_FILE=$HOME/xsdk/cmake/xsdk.cmake
#   cmake --build build-xbox

set(CMAKE_C_STANDARD 17)

add_executable(re4coop
    src/main_xsdk.c
    src/render_xsdk.c
    src/draw_scene.c
    src/game.c
    src/collision.c
    src/map.c
)

# Gera o .xex e compila os shaders GLSL (funcoes do cmake/xsdk.cmake)
xsdk_add_xex(re4coop)
xsdk_add_shaders(re4coop shaders/map.vert shaders/map.frag)
