#ifndef GX_ARRAY_H
#define GX_ARRAY_H

// 360 port: Aurora's GXSetArray needs the array's size in bytes (it decodes vertices on the CPU and bounds-checks every
// index against it). The GameCube original passed only the stride. Helpers to get the sizes the original data implies.

#include "types.h"
#include "model.h"

// Bytes of one section of a model bin whose size the header does not store (colour array pClr, texture-coordinate
// array pTex): the distance to the next section start. The arrays can never run past it, and padding only makes the
// bound looser (Aurora just needs it to be >= what the display lists index).
static inline u32 ModelSectionBytes(const cModelData* d, const void* section)
{
    const u8* s = (const u8*) section;
    const u8* next = 0;
    const void* cand[] = {d->pClr, d->pTex, d->pHead, d->pWeight, d->pParts, d->vtxOrig, d->nrmOrig};
    for (unsigned i = 0; i < sizeof(cand) / sizeof(cand[0]); i++) {
        const u8* c = (const u8*) cand[i];
        if (c > s && (next == 0 || c < next)) {
            next = c;
        }
    }
    return next ? (u32) (next - s) : 0x10000;   // last section: unknown, generous (never the case for pClr/pTex)
}

// Water / sand grids (Espgen42/43/45): (Width + 1) x (Height + 1) points, one Vec each.
#define GRID_POINTS(p) ((u32) ((p)->Width + 1) * (u32) ((p)->Height + 1))
#define GRID_VEC_BYTES(p) (GRID_POINTS(p) * (u32) sizeof(Vec))

#endif
