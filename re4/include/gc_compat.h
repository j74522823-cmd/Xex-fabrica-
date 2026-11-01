#ifndef GC_COMPAT_H
#define GC_COMPAT_H

// 360 port: things the GameCube code reached by address or by Gekko-only instruction.
#include "types.h"

// The GameCube's 16 KB locked cache sat at 0xE0000000 (LCEnable): the skinning matrix palette (trans.cpp, ROMtx 0x30
// bytes each) and pendulum.cpp's work area live there. On the 360 it is an ordinary buffer.
#ifdef __cplusplus
extern "C" {
#endif
extern u8 g_LockedCache[0x4000];
#ifdef __cplusplus
}
#endif
#define LC_BASE ((u8*) g_LockedCache)

#endif
