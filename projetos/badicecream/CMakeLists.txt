# Bad Ice-Cream para o Xbox 360 (fabrica de XEX). Os dados do jogo ficam em runtime_data.zip.
cmake_minimum_required(VERSION 3.25)
project(badicecream C CXX)

add_executable(badicecream
	platform_xbox360.cpp
	src/engine.cpp src/render.cpp src/game.cpp)
target_include_directories(badicecream PRIVATE src)
set_target_properties(badicecream PROPERTIES CXX_STANDARD 20 CXX_EXTENSIONS ON)
target_compile_options(badicecream PRIVATE -Wall -Wextra)
xsdk_add_shaders(badicecream sprite.vert sprite.frag)
xsdk_add_xex(badicecream NAME "Bad Ice-Cream")
