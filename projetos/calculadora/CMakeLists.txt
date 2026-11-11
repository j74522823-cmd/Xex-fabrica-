cmake_minimum_required(VERSION 3.25)
project(calculadora C)

add_executable(calculadora main.c)
set_target_properties(calculadora PROPERTIES C_STANDARD 17 C_EXTENSIONS ON)
target_compile_options(calculadora PRIVATE -Wall -Wextra -Werror)
xsdk_add_shaders(calculadora calc.vert calc.frag)
xsdk_add_xex(calculadora)
