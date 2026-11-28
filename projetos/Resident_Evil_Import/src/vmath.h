/* vmath.h - vetores e matrizes 4x4 (colunas, como o GLSL). */
#ifndef VMATH_H
#define VMATH_H

#include <math.h>

typedef struct { float x, y, z; } vec3;

static inline vec3 v3(float x, float y, float z) { vec3 r = {x, y, z}; return r; }
static inline vec3 v3_add(vec3 a, vec3 b) { return v3(a.x + b.x, a.y + b.y, a.z + b.z); }
static inline vec3 v3_sub(vec3 a, vec3 b) { return v3(a.x - b.x, a.y - b.y, a.z - b.z); }
static inline vec3 v3_scale(vec3 a, float s) { return v3(a.x * s, a.y * s, a.z * s); }
static inline float v3_dot(vec3 a, vec3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
static inline vec3 v3_cross(vec3 a, vec3 b) {
    return v3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
}
static inline float v3_len(vec3 a) { return sqrtf(v3_dot(a, a)); }
static inline vec3 v3_norm(vec3 a) {
    float l = v3_len(a);
    return l > 1e-8f ? v3_scale(a, 1.0f / l) : v3(0, 0, 0);
}
static inline float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }
static inline float lerpf(float a, float b, float t) { return a + (b - a) * t; }

/* m[col*4 + row] */
typedef struct { float m[16]; } mat4;

static inline mat4 m4_identity(void) {
    mat4 r = {{1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1}};
    return r;
}

static inline mat4 m4_mul(mat4 a, mat4 b) {
    mat4 r;
    for (int c = 0; c < 4; c++)
        for (int rr = 0; rr < 4; rr++) {
            float s = 0;
            for (int k = 0; k < 4; k++) s += a.m[k * 4 + rr] * b.m[c * 4 + k];
            r.m[c * 4 + rr] = s;
        }
    return r;
}

/* Projecao perspectiva, mao direita, profundidade 0..1 (estilo Direct3D, como a Xenos). */
static inline mat4 m4_perspective(float fovy, float aspect, float zn, float zf) {
    float f = 1.0f / tanf(fovy * 0.5f);
    mat4 r = {{0}};
    r.m[0] = f / aspect;
    r.m[5] = f;
    r.m[10] = zf / (zn - zf);
    r.m[11] = -1.0f;
    r.m[14] = zn * zf / (zn - zf);
    return r;
}

static inline mat4 m4_look_at(vec3 eye, vec3 target, vec3 up) {
    vec3 f = v3_norm(v3_sub(target, eye));
    vec3 s = v3_norm(v3_cross(f, up));
    vec3 u = v3_cross(s, f);
    mat4 r = m4_identity();
    r.m[0] = s.x; r.m[4] = s.y; r.m[8] = s.z;
    r.m[1] = u.x; r.m[5] = u.y; r.m[9] = u.z;
    r.m[2] = -f.x; r.m[6] = -f.y; r.m[10] = -f.z;
    r.m[12] = -v3_dot(s, eye);
    r.m[13] = -v3_dot(u, eye);
    r.m[14] = v3_dot(f, eye);
    return r;
}

/* Translacao * rotacao em Y * escala */
static inline mat4 m4_trs_y(vec3 t, float yaw, vec3 s) {
    float c = cosf(yaw), sn = sinf(yaw);
    mat4 r = m4_identity();
    r.m[0] = c * s.x;   r.m[2] = -sn * s.x;
    r.m[5] = s.y;
    r.m[8] = sn * s.z;  r.m[10] = c * s.z;
    r.m[12] = t.x; r.m[13] = t.y; r.m[14] = t.z;
    return r;
}

#endif
