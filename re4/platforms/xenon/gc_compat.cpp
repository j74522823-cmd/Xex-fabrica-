#include "gc_compat.h"
#include "vec.h"

extern "C" {
// 32-byte aligned like the real locked cache lines.
u8 g_LockedCache[0x4000] __attribute__((aligned(32)));
}

// Projective transform of a point by a 4x4 matrix with the divide by w (Gekko had this as paired singles).
extern "C" void RE4_MTX44MultVec(const Mtx44 m, const Vec* src, Vec* dst)
{
    float x = src->x, y = src->y, z = src->z;
    float w = m[3][0] * x + m[3][1] * y + m[3][2] * z + m[3][3];
    float inv = 1.0f / w;
    dst->x = (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3]) * inv;
    dst->y = (m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3]) * inv;
    dst->z = (m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3]) * inv;
}
