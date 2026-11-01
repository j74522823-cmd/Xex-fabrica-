#ifndef ATARI_INIT_H
#define ATARI_INIT_H

#include "atariInfo.h"

// Float constants must reach the call as pseudos (cse then shares the 0.0 with the `pos = 0`
// stores that follow, and the 1000.0 load gets the longer dependence chain the original schedules
// first): pass them through an inline whose float parameters are the arguments.
static inline void AtariInit(cAtariInfo* at, f32 x, f32 y, f32 z, f32 rx, f32 rz, f32 w, f32 h, int parts,
                             int flags, int cnt)
{
    at->init(x, y, z, rx, rz, w, h, parts, flags, cnt);
}

#endif
