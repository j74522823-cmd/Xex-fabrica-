#ifndef OS_VI_H
#define OS_VI_H

#include "types.h"
#include "gx.h"

// Dolphin OS/VI entry points used by game code (the SDK headers are CodeWarrior-only).
extern "C" {
// OSPanic: declared by Aurora's dolphin/os.h
u32 OSGetProgressiveMode();
void OSSetProgressiveMode(u32 on);
u32 VIGetTvFormat();
u32 VIGetDTVStatus();
void VIConfigure(const GXRenderModeObj* rm);
void VIFlush();
void DCInvalidateRange(void* addr, u32 nBytes);
void DCStoreRange(void* addr, u32 nBytes);
}

#endif
