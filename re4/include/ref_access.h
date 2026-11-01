#ifndef REF_ACCESS_H
#define REF_ACCESS_H

#include "types.h"
#include "vec.h"

// Reads and writes of a variable through a reference parameter. Each helper below has one or two use
// sites whose plain form still compiles differently with the shipped-build-mem-flags compiler (checked
// 2026-09-22 with variant.sh: model.cpp U8Set, sce_sys.cpp U8SetI, room_jmp.cpp S8Set, t_esp DEACTIVATE
// ISet, trans.cpp IRef, and VecSet in r202 / r208 / r219); the reference makes the access a scalar MEM
// that GCC 2.95 orders and reloads differently from a member access. Do not add uses: a plain store is the
// form everywhere else.
static inline void U8Set(u8& d, u8 v) { d = v; }
static inline void U8SetI(u8& d, int v) { d = v; }
static inline void S8Set(s8& d, s8 v) { d = v; }
static inline void ISet(int& d, int v) { d = v; }

static inline int IRef(int& v) { return v; }

// Fill a Vec (x, y, z) and return it: the element stores go through the vector's address, so the
// address pseudo is shared with a call that follows (`mr r4, rX`) (model, r202, r208, r219).
static inline Vec* VecSet(Vec* v, f32 x, f32 y, f32 z)
{
    v->x = x;
    v->y = y;
    v->z = z;
    return v;
}

#endif
