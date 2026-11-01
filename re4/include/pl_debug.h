#ifndef PL_DEBUG_H
#define PL_DEBUG_H

#include "types.h"

// Player debug counters (game/pl_debug.cpp). pl_debug.cpp does not include this header: PlCapNum is
// uninitialised and a declaration ahead of its definition would reorder the unit's .bss.

extern u8 PlCapNum[25];   // captures per weapon (r22c counts the shooting gallery hits into it)

#endif
