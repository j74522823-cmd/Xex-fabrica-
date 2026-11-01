#ifndef EM_DM_VAL_H
#define EM_DM_VAL_H

#include "types.h"

// Weapon damage tables (game/em_dm_val.cpp): GetWepDmVal (declared in em10.h) combines them for a hit.

// Firepower multiplier per weapon (0..0x2D) and upgrade level (item.cpp shows the tune-up ratio from it).
extern f32 WeaponLevelTbl[0x2E][7];

#endif
