/* SN ProDG libm (newlib 1.8.2 fdlibm): sqrt() (double). The fdlibm source is compiled as C++ through this
 * wrapper (static consts defined in an included file are dropped when folded, tables keep their
 * small-data placement); the game's math (game/math_sub.cpp, the sinf/cosf/atan2f/sqrtf calls of the
 * player, camera and enemy code) resolves to these. */
#include "fdlibm/e_sqrt.c"
