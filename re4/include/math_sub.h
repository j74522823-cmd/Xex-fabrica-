#ifndef MATH_SUB_H
#define MATH_SUB_H

#include "types.h"
#include "vec.h"
#include "db_log.h"

// 360 port: the SDK's volatile-asm fabsf (a scheduling barrier for byte-matching) is gone; libm's fabsf is used.
#include <math.h>

// Column `c` of a matrix read into a Vec.
static inline void getColumn(Mtx m, int c, Vec* v) { v->x = m[0][c]; v->y = m[1][c]; v->z = m[2][c]; }

// Matrix from four columns (right, up, look, position).
static inline void MTXSetColumns(Mtx mat, Vec& v0, Vec& v1, Vec& v2, Vec& v3)
{
    mat[0][0] = v0.x; mat[1][0] = v0.y; mat[2][0] = v0.z;
    mat[0][1] = v1.x; mat[1][1] = v1.y; mat[2][1] = v1.z;
    mat[0][2] = v2.x; mat[1][2] = v2.y; mat[2][2] = v2.z;
    mat[0][3] = v3.x; mat[1][3] = v3.y; mat[2][3] = v3.z;
}

#include "math_sub_decl.h"

#endif
