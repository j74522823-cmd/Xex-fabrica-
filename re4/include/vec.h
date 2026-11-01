#ifndef VEC_H
#define VEC_H

// Dolphin SDK vector/matrix types and the PS* routines used by game code. The SDK headers in
// include/dolphin/ pull in the CodeWarrior libc and cannot be compiled by ProDG/GCC, so game
// units include this instead. Shares the dolphin/mtx.h guard so both can coexist.

#include "types.h"

// 360 port: Aurora's <dolphin/mtx.h> declares these and maps the PS* (Gekko paired-single) names to its portable C
// versions (#define PSMTXMultVec MTXMultVec ...). RE4's own declarations of the PS* functions would bypass that mapping.
#include <dolphin/mtx.h>

// Aurora declares PSMTX44MultVec for Gekko only and has no portable body for it: platforms/xenon/gc_compat.cpp has one.
#ifdef __cplusplus
extern "C" {
#endif
void RE4_MTX44MultVec(const Mtx44 m, const Vec* src, Vec* dst);
#ifdef __cplusplus
}
#endif
#define PSMTX44MultVec RE4_MTX44MultVec

// Mtx copy as the original's inlined word loop (three rows of four f32 through row pointers); a plain
// block. The loop shape is a register-allocation lever: units whose bytes need another one keep a
// local variant (motion.cpp MTX_COPY_DOWN, at_mod.cpp / ss_pzzl.cpp MTX_COPY_DO, sce_at.cpp
// MTX_COPY_LATE_DST), see docs/matching.md "Mtx copy loops".
#define MTX_COPY(src, dst)               \
    {                                    \
        MtxPtr d_ = (dst);               \
        MtxPtr s_ = (src);               \
        int i_ = 3;                      \
        int j_;                          \
        f32* sp_;                        \
        f32* dp_;                        \
        while (i_--) {                   \
            dp_ = *d_;                   \
            sp_ = *s_;                   \
            for (j_ = 0; j_ < 4; j_++) { \
                *dp_++ = *sp_++;         \
            }                            \
            d_++;                        \
            s_++;                        \
        }                                \
    }

#endif
