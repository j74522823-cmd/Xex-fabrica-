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
    src/t_*/*.cpp
    src/lib/texPalette.c src/lib/fileCache.c)   # charPipeline + its file cache: not in Aurora
# Debug editors (src/Tools, src/tools) stay out until the game itself runs.
# Gekko exception handler reads OSContext gpr/srr0: nothing to port, xsdk has its own fault handling.
list(FILTER RE4_SOURCES EXCLUDE REGEX "src/game/exception\\.cpp$")
# Debug tools, the SN libc (xsdk has its own) and the t_esp debug port: see tools/xenon/excluded.txt
# src/game/*.c is the SN compiler's C library (stdio, locale, string, malloc...): newlib in xsdk provides all of it.
list(FILTER RE4_SOURCES EXCLUDE REGEX "src/game/[^/]*\\.c$")
list(FILTER RE4_SOURCES EXCLUDE REGEX "src/[Tt]ools/")
list(FILTER RE4_SOURCES EXCLUDE REGEX "src/t_esp/(db_port|t_esp)\\.cpp$")
# The t_* directories are the debug editors' screens (event / camera / light / id tools): they call the Tools code above.
list(FILTER RE4_SOURCES EXCLUDE REGEX "src/t_[A-Za-z_]*/")
list(FILTER RE4_SOURCES EXCLUDE REGEX "src/game/db_widget\\.cpp$")
# Direct GameCube-debugger I/O (PCinit/PCopen...), the HIO/PC host link of the debug build.
# list(FILTER ... ) of the files that need it goes here once they are identified.

# ---- REL overlays, linked statically --------------------------------------------------------------------------------------
# On the GameCube the stage / weapon / enemy modules (config/G4BE08) were separate RELs, each linked on its own, so they
# define the same global names. tools/xenon/gen_modules.py lists each module's sources and writes the table that maps a REL's
# module id to its entry points. Every module is built with -DREL_MODULE=<name> (as configure.py does), partially linked into
# one object, and all of its symbols are made local but <name>__prolog / __epilog / __unresolved. OSLink (os_compat.cpp) then
# hands the game those entry points instead of relocating the REL it read from the disc.
set(RE4_GEN "${CMAKE_CURRENT_BINARY_DIR}/gen")
execute_process(COMMAND python3 "${CMAKE_CURRENT_SOURCE_DIR}/tools/xenon/gen_modules.py" "${CMAKE_CURRENT_SOURCE_DIR}" "${RE4_GEN}"
    RESULT_VARIABLE RE4_GEN_RESULT)
if (NOT RE4_GEN_RESULT EQUAL 0)
  message(FATAL_ERROR "gen_modules.py failed")
endif ()
include("${RE4_GEN}/modules.cmake")
list(REMOVE_ITEM RE4_SOURCES ${RE4_MODULE_SOURCES})   # what is left is the DOL: the main game

set(RE4_AURORA_LIBS aurora::main aurora::core aurora::gx aurora::gd aurora::si aurora::vi aurora::pad
    aurora::mtx aurora::os aurora::dvd aurora::card vulkan4xenon)

function(re4_settings tgt)
  target_include_directories(${tgt} PRIVATE include src)
  # Aurora's <dolphin/...> headers must win over RE4's own include/dolphin/*.h (the GameCube SDK headers), as in
  # tools/xenon/check_compile.sh.
  target_include_directories(${tgt} BEFORE PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/extern/aurora/include")
  target_compile_definitions(${tgt} PRIVATE
      TARGET_PC AURORA                 # Aurora's software GX command stream (GXWGFifo is not a memory address here)
      BUILD_VERSION=1 VERSION_G4BE08 NDEBUG=1)
  # The decomp is GCC 2.95 C++/C: be lenient. Do NOT add -fsigned-char (Dusklight does, for CodeWarrior code): PowerPC char is
  # unsigned and the SN compiler used that default.
  target_compile_options(${tgt} PRIVATE -fpermissive -w)
  set_target_properties(${tgt} PROPERTIES C_STANDARD 11 C_EXTENSIONS ON CXX_STANDARD 17 CXX_EXTENSIONS ON)
endfunction()

file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/tools/xenon/rel_exports.txt" RE4_REL_EXPORTS REGEX "^[^#]")
set(RE4_KEEP_EXPORTS)
set(RE4_WEAKEN_EXPORTS)
foreach (X ${RE4_REL_EXPORTS})
  list(APPEND RE4_KEEP_EXPORTS --keep-global-symbol=${X})
  list(APPEND RE4_WEAKEN_EXPORTS --weaken-symbol=${X})
endforeach ()
set(RE4_MODULE_OBJECTS)
foreach (M ${RE4_MODULES})
  add_library(rel_${M} OBJECT ${RE4_MOD_${M}_SRCS})
  re4_settings(rel_${M})
  target_compile_definitions(rel_${M} PRIVATE REL_MODULE=${M})
  target_link_libraries(rel_${M} PRIVATE ${RE4_AURORA_LIBS})
  set(OBJ "${CMAKE_CURRENT_BINARY_DIR}/rel/${M}.o")
  add_custom_command(OUTPUT "${OBJ}"
      COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_CURRENT_BINARY_DIR}/rel"
      COMMAND ${XSDK_PREFIX}ld -r -d --force-group-allocation -o "${OBJ}.1" $<TARGET_OBJECTS:rel_${M}>
      COMMAND ${XSDK_PREFIX}objcopy --redefine-sym _prolog=${M}__prolog --redefine-sym _epilog=${M}__epilog
              --redefine-sym _unresolved=${M}__unresolved "${OBJ}.1" "${OBJ}.2"
      COMMAND ${XSDK_PREFIX}objcopy --keep-global-symbol=${M}__prolog --keep-global-symbol=${M}__epilog
              --keep-global-symbol=${M}__unresolved ${RE4_KEEP_EXPORTS} ${RE4_WEAKEN_EXPORTS} "${OBJ}.2" "${OBJ}"
      DEPENDS $<TARGET_OBJECTS:rel_${M}> COMMAND_EXPAND_LISTS VERBATIM)
  set_source_files_properties("${OBJ}" PROPERTIES EXTERNAL_OBJECT TRUE GENERATED TRUE)
  list(APPEND RE4_MODULE_OBJECTS "${OBJ}")
endforeach ()

# First link: the game's own `int main()` (src/game/main.cpp) is the entry; platforms/xenon/main_xenon.cpp comes later.
add_executable(re4 ${RE4_SOURCES} ${RE4_MODULE_OBJECTS} "${RE4_GEN}/rel_table.cpp" "${RE4_GEN}/rel_unresolved.cpp"
    platforms/xenon/gc_compat.cpp platforms/xenon/os_compat.cpp platforms/xenon/audio_stubs.cpp platforms/xenon/legacy_syms.cpp)
re4_settings(re4)
target_link_libraries(re4 PRIVATE ${RE4_AURORA_LIBS})

xsdk_add_xex(re4 TITLE_ID 0x52453420 NAME "RE4" VERSION 0.0.1.0)   # TITLE_ID is a placeholder
