#ifndef CONS_H
#define CONS_H

#include "types.h"

// Room resource limits (game/cons.cpp): work counts per room, indexed by CONS_ROOM_INDEX (PS2).
enum CONS_ROOM_INDEX {
    CONS_R_NEM = 0,
    CONS_R_NOBJ = 1,
    CONS_R_NESP = 2,
    CONS_R_NESPGEN = 3,
    CONS_R_NCTRL = 4,
    CONS_R_NLIGHT = 5,
    CONS_R_NPARTS = 6,
    CONS_R_NMODELINFO = 7,
    CONS_R_NPRIM = 8,
    CONS_R_NEVT = 9,
    CONS_R_NSAT = 10,
    CONS_R_NEAT = 11
};

u32 ConsGetRoomValue(u32 id);

#endif
