cmake_minimum_required(VERSION 3.25)
project(re4coop C)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_EXTENSIONS ON)

add_executable(re4coop
    src/main_xsdk.c
    src/render_xsdk.c
    src/draw_scene.c
    src/game.c
    src/collision.c
    src/map.c
)

target_compile_options(re4coop PRIVATE -Wall -Wextra)
target_include_directories(re4coop PRIVATE src)
xsdk_add_shaders(re4coop shaders/map.vert shaders/map.frag)
xsdk_add_xex(re4coop)

