#include "gc_compat.h"

extern "C" {
// 32-byte aligned like the real locked cache lines.
u8 g_LockedCache[0x4000] __attribute__((aligned(32)));
}
