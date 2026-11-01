#ifndef GX_H
#define GX_H

// 360 port: the trimmed ProDG-compatible GX header is replaced by Aurora's real GX API
// (aurora-xenon include/dolphin/gx.h). The original is kept in gx_prodg_orig.h.txt.
// Aurora's GXVert.h inlines write the vertex stream into Aurora's own command stream,
// which is the "FIFO" layer the GameCube build wrote to 0xCC008000.

#include "types.h"
#include <dolphin/gx.h>

// ---- RE4 compat over Aurora ------------------------------------------------------------
// The original wrote vertex data straight to the GameCube write-gather pipe. Aurora keeps a
// software command stream behind GXParam1*/GXCmd1*, so these inlines keep the call sites
// unchanged. (GXPosition3f32, GXColor4u8, GXTexCoord2f32 ... are real Aurora functions.)
#ifdef __cplusplus
extern "C" {
#endif
static inline void GXMatrixIndex1u8(u8 idx) { GXParam1u8(idx); }

// Declared by the SDK but missing from Aurora's public headers:
void GXSetTevIndBumpXYZ(GXTevStageID tev_stage, GXIndTexStageID ind_stage, GXIndTexMtxID matrix_sel);
// Not implemented by Aurora (hardware bounding-box / indirect mask registers). No-ops for now.
static inline void GXClearBoundingBox(void) {}
static inline void __GXSetIndirectMask(u32 mask) { (void)mask; } // TODO: map onto Aurora's indirect state
#ifdef __cplusplus
}
#endif

#endif
