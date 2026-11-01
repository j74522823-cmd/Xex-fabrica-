# Resident Evil 4 (GameCube debug build decomp) -> Xbox 360 through xsdk + aurora-xenon.
#
# STATUS: skeleton, NOT built on a real xsdk toolchain yet (see docs/360-port.md).
# Modelled on xenosworks/dusklight-xenon's CMakeLists.txt (the `if (XSDK)` parts).
#
#   cmake -S . -B build -DCMAKE_TOOLCHAIN_FILE=<xsdk>/cmake/xsdk.cmake -DXSDK=ON
#
# Expected layout next to this repo:  ../vulkan4xenon  ../glslang-xenon  extern/aurora (aurora-xenon, branch xenon)
cmake_minimum_required(VERSION 3.25)
project(re4 C CXX)

if (NOT XSDK)
  message(FATAL_ERROR "This port only targets the Xbox 360 through xsdk: pass xsdk's toolchain file and -DXSDK=ON")
endif ()

# ---- Aurora (GX / VI / PAD / DVD / CARD / OS / MTX) -------------------------------------------------------------
set(AURORA_GFX_BACKEND vulkan4xenon CACHE STRING "What draws GX" FORCE)
set(AURORA_NOD_PROVIDER iso CACHE STRING "" FORCE)        # plain GameCube images (the two debug discs)
set(AURORA_SDL3_PROVIDER system CACHE STRING "" FORCE)    # SDL-xenon
set(VULKAN4XENON_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../vulkan4xenon" CACHE PATH "vulkan4xenon repository, built")
add_library(vulkan4xenon STATIC IMPORTED)
set_target_properties(vulkan4xenon PROPERTIES
    IMPORTED_LOCATION "${VULKAN4XENON_DIR}/build/libvulkan4xenon.a"
    INTERFACE_INCLUDE_DIRECTORIES "${VULKAN4XENON_DIR}/include;${VULKAN4XENON_DIR}/third_party/vulkan-headers/include")
set(GLSLANG_XENON_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../glslang-xenon" CACHE PATH "glslang-xenon repository")
set(ENABLE_OPT OFF CACHE BOOL "" FORCE)
set(ENABLE_HLSL OFF CACHE BOOL "" FORCE)
set(ENABLE_GLSLANG_BINARIES OFF CACHE BOOL "" FORCE)
set(GLSLANG_TESTS OFF CACHE BOOL "" FORCE)
set(BUILD_EXTERNAL OFF CACHE BOOL "" FORCE)
set(GLSLANG_ENABLE_INSTALL OFF CACHE BOOL "" FORCE)
add_subdirectory("${GLSLANG_XENON_DIR}" glslang EXCLUDE_FROM_ALL)

# Frame pools sized like Dusklight's; RE4 has a 24 MB GameCube budget, so these are generous. CPU and GPU share 512 MB.
set(AURORA_VERTEX_POOL_SIZE 2097152 CACHE STRING "" FORCE)
set(AURORA_UNIFORM_POOL_SIZE 2097152 CACHE STRING "" FORCE)
set(AURORA_INDEX_POOL_SIZE 1048576 CACHE STRING "" FORCE)
set(AURORA_STORAGE_POOL_SIZE 2097152 CACHE STRING "" FORCE)
set(AURORA_TEXTURE_UPLOAD_POOL_SIZE 8388608 CACHE STRING "" FORCE)
add_subdirectory(extern/aurora)

# ---- The game ---------------------------------------------------------------------------------------------------
# Everything outside src/lib. src/lib is the Dolphin SDK (replaced by Aurora), CRI (audio/video, TODO), the SN runtime and
# libm/libgcc (newlib provides them).
file(GLOB_RECURSE RE4_SOURCES CONFIGURE_DEPENDS
    src/game/*.c src/game/*.cpp
    src/em*/*.c   src/em*/*.cpp
    src/wep*/*.c  src/wep*/*.cpp
    src/pl*/*.c   src/pl*/*.cpp
    src/st*/*.c   src/st*/*.cpp
    src/Sscrn/*.cpp
    src/t_*/*.cpp)
# Debug editors (src/Tools, src/tools) stay out until the game itself runs.
# Gekko exception handler reads OSContext gpr/srr0: nothing to port, xsdk has its own fault handling.
list(FILTER RE4_SOURCES EXCLUDE REGEX "src/game/exception\\.cpp$")
# Debug tools, the SN libc (xsdk has its own) and the t_esp debug port: see tools/xenon/excluded.txt
list(FILTER RE4_SOURCES EXCLUDE REGEX "src/game/(sprintf|sscanf|fprintf|printf)\\.c$")
list(FILTER RE4_SOURCES EXCLUDE REGEX "src/[Tt]ools/")
list(FILTER RE4_SOURCES EXCLUDE REGEX "src/t_esp/(db_port|t_esp)\\.cpp$")
# Direct GameCube-debugger I/O (PCinit/PCopen...), the HIO/PC host link of the debug build.
# list(FILTER ... ) of the files that need it goes here once they are identified.

add_executable(re4 ${RE4_SOURCES} platforms/xenon/main_xenon.cpp)
target_include_directories(re4 PRIVATE include src)
target_compile_definitions(re4 PRIVATE
    TARGET_PC AURORA                 # Aurora's software GX command stream (GXWGFifo is not a memory address here)
    BUILD_VERSION=1 VERSION_G4BE08 NDEBUG=1)
# The decomp is GCC 2.95 C++/C: be lenient. Do NOT add -fsigned-char (Dusklight does, for CodeWarrior code): PowerPC char is
# unsigned and the SN compiler used that default.
target_compile_options(re4 PRIVATE -fpermissive -w)
set_target_properties(re4 PROPERTIES C_STANDARD 11 C_EXTENSIONS ON CXX_STANDARD 17 CXX_EXTENSIONS ON)
target_link_libraries(re4 PRIVATE aurora::main aurora::core aurora::gx aurora::gd aurora::si aurora::vi aurora::pad
    aurora::mtx aurora::os aurora::dvd aurora::card vulkan4xenon)

xsdk_add_xex(re4 TITLE_ID 0x52453420 NAME "RE4" VERSION 0.0.1.0)   # TITLE_ID is a placeholder
