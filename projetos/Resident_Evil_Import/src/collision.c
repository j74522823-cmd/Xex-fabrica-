/* collision.c */
#include "collision.h"

#include <stdlib.h>
#include <string.h>

#define WALKABLE_NY 0.55f        /* normal.y acima disso = chao andavel (~57 graus) */

static int cell_index(const Collision *c, int cx, int cz) { return cz * c->cells_x + cx; }

static void cell_range(const Collision *c, float minx, float maxx, float minz, float maxz,
                       int *x0, int *x1, int *z0, int *z1) {
    *x0 = (int)((minx - c->origin_x) / c->cell_size);
    *x1 = (int)((maxx - c->origin_x) / c->cell_size);
    *z0 = (int)((minz - c->origin_z) / c->cell_size);
    *z1 = (int)((maxz - c->origin_z) / c->cell_size);
    if (*x0 < 0) *x0 = 0;
    if (*z0 < 0) *z0 = 0;
    if (*x1 >= c->cells_x) *x1 = c->cells_x - 1;
    if (*z1 >= c->cells_z) *z1 = c->cells_z - 1;
}

void collision_build(Collision *col, const Map *map, float cell_size) {
    memset(col, 0, sizeof *col);
    col->cell_size = cell_size;
    col->bounds_min = map->bounds_min;
    col->bounds_max = map->bounds_max;
    col->origin_x = map->bounds_min.x - cell_size;
    col->origin_z = map->bounds_min.z - cell_size;
    col->cells_x = (int)((map->bounds_max.x - col->origin_x) / cell_size) + 2;
    col->cells_z = (int)((map->bounds_max.z - col->origin_z) / cell_size) + 2;
    int ncells = col->cells_x * col->cells_z;

    uint32_t ntris = map->num_indices / 3;
    col->tris = (ColTri *)malloc(sizeof(ColTri) * ntris);
    uint32_t kept = 0;
    for (uint32_t i = 0; i < ntris; i++) {
        const float *pa = map->vertices[map->indices[i * 3 + 0]].pos;
        const float *pb = map->vertices[map->indices[i * 3 + 1]].pos;
        const float *pc = map->vertices[map->indices[i * 3 + 2]].pos;
        ColTri t;
        t.a = v3(pa[0], pa[1], pa[2]);
        t.b = v3(pb[0], pb[1], pb[2]);
        t.c = v3(pc[0], pc[1], pc[2]);
        vec3 n = v3_cross(v3_sub(t.b, t.a), v3_sub(t.c, t.a));
        float len = v3_len(n);
        if (len < 1e-6f) continue;            /* triangulo degenerado */
        t.n = v3_scale(n, 1.0f / len);
        col->tris[kept++] = t;
    }
    col->num_tris = kept;

    /* Duas passadas: contar, depois preencher. */
    uint32_t *count = (uint32_t *)calloc((size_t)ncells + 1, sizeof(uint32_t));
    for (int pass = 0; pass < 2; pass++) {
        for (uint32_t i = 0; i < kept; i++) {
            const ColTri *t = &col->tris[i];
            float minx = fminf(t->a.x, fminf(t->b.x, t->c.x)), maxx = fmaxf(t->a.x, fmaxf(t->b.x, t->c.x));
            float minz = fminf(t->a.z, fminf(t->b.z, t->c.z)), maxz = fmaxf(t->a.z, fmaxf(t->b.z, t->c.z));
            int x0, x1, z0, z1;
            cell_range(col, minx, maxx, minz, maxz, &x0, &x1, &z0, &z1);
            for (int z = z0; z <= z1; z++)
                for (int x = x0; x <= x1; x++) {
                    int ci = cell_index(col, x, z);
                    if (pass == 0) count[ci]++;
                    else col->cell_tris[col->cell_start[ci] + count[ci]++] = i;
                }
        }
        if (pass == 0) {
            col->cell_start = (uint32_t *)malloc(sizeof(uint32_t) * ((size_t)ncells + 1));
            uint32_t sum = 0;
            for (int c = 0; c < ncells; c++) {
                col->cell_start[c] = sum;
                sum += count[c];
            }
            col->cell_start[ncells] = sum;
            col->cell_tris = (uint32_t *)malloc(sizeof(uint32_t) * (sum ? sum : 1));
            memset(count, 0, sizeof(uint32_t) * ((size_t)ncells + 1));
        }
    }
    free(count);
    col->stamp = (uint32_t *)calloc(kept ? kept : 1, sizeof(uint32_t));
}

void collision_free(Collision *col) {
    free(col->tris);
    free(col->cell_start);
    free(col->cell_tris);
    free(col->stamp);
    memset(col, 0, sizeof *col);
}

static void new_stamp(Collision *col) {
    if (++col->stamp_value == 0) {
        memset(col->stamp, 0, sizeof(uint32_t) * col->num_tris);
        col->stamp_value = 1;
    }
}

int collision_ground(Collision *col, float x, float z, float y_top, float y_bottom,
                     float *out_y, vec3 *out_normal) {
    int cx = (int)((x - col->origin_x) / col->cell_size);
    int cz = (int)((z - col->origin_z) / col->cell_size);
    if (cx < 0 || cz < 0 || cx >= col->cells_x || cz >= col->cells_z) return 0;
    int ci = cell_index(col, cx, cz);
    int found = 0;
    float best = y_bottom;
    for (uint32_t k = col->cell_start[ci]; k < col->cell_start[ci + 1]; k++) {
        const ColTri *t = &col->tris[col->cell_tris[k]];
        if (fabsf(t->n.y) < WALKABLE_NY) continue;
        /* baricentricas no plano XZ */
        float d = (t->b.z - t->c.z) * (t->a.x - t->c.x) + (t->c.x - t->b.x) * (t->a.z - t->c.z);
        if (fabsf(d) < 1e-9f) continue;
        float l1 = ((t->b.z - t->c.z) * (x - t->c.x) + (t->c.x - t->b.x) * (z - t->c.z)) / d;
        float l2 = ((t->c.z - t->a.z) * (x - t->c.x) + (t->a.x - t->c.x) * (z - t->c.z)) / d;
        float l3 = 1.0f - l1 - l2;
        const float e = -1e-4f;
        if (l1 < e || l2 < e || l3 < e) continue;
        float y = l1 * t->a.y + l2 * t->b.y + l3 * t->c.y;
        if (y <= y_top && y > best) {
            best = y;
            found = 1;
            if (out_normal) *out_normal = t->n.y < 0 ? v3_scale(t->n, -1) : t->n;
        }
    }
    if (found && out_y) *out_y = best;
    return found;
}

static vec3 closest_point_tri(vec3 p, const ColTri *t) {
    /* Ericson, Real-Time Collision Detection, 5.1.5 */
    vec3 a = t->a, b = t->b, c = t->c;
    vec3 ab = v3_sub(b, a), ac = v3_sub(c, a), ap = v3_sub(p, a);
    float d1 = v3_dot(ab, ap), d2 = v3_dot(ac, ap);
    if (d1 <= 0 && d2 <= 0) return a;
    vec3 bp = v3_sub(p, b);
    float d3 = v3_dot(ab, bp), d4 = v3_dot(ac, bp);
    if (d3 >= 0 && d4 <= d3) return b;
    float vc = d1 * d4 - d3 * d2;
    if (vc <= 0 && d1 >= 0 && d3 <= 0) return v3_add(a, v3_scale(ab, d1 / (d1 - d3)));
    vec3 cp = v3_sub(p, c);
    float d5 = v3_dot(ab, cp), d6 = v3_dot(ac, cp);
    if (d6 >= 0 && d5 <= d6) return c;
    float vb = d5 * d2 - d1 * d6;
    if (vb <= 0 && d2 >= 0 && d6 <= 0) return v3_add(a, v3_scale(ac, d2 / (d2 - d6)));
    float va = d3 * d6 - d5 * d4;
    if (va <= 0 && (d4 - d3) >= 0 && (d5 - d6) >= 0)
        return v3_add(b, v3_scale(v3_sub(c, b), (d4 - d3) / ((d4 - d3) + (d5 - d6))));
    float denom = 1.0f / (va + vb + vc);
    float v = vb * denom, w = vc * denom;
    return v3_add(a, v3_add(v3_scale(ab, v), v3_scale(ac, w)));
}

int collision_push_sphere(Collision *col, vec3 *center, float radius) {
    int hit = 0;
    for (int iter = 0; iter < 3; iter++) {
        int x0, x1, z0, z1;
        cell_range(col, center->x - radius, center->x + radius, center->z - radius, center->z + radius,
                   &x0, &x1, &z0, &z1);
        new_stamp(col);
        int moved = 0;
        for (int z = z0; z <= z1; z++)
            for (int x = x0; x <= x1; x++) {
                int ci = cell_index(col, x, z);
                for (uint32_t k = col->cell_start[ci]; k < col->cell_start[ci + 1]; k++) {
                    uint32_t ti = col->cell_tris[k];
                    if (col->stamp[ti] == col->stamp_value) continue;
                    col->stamp[ti] = col->stamp_value;
                    const ColTri *t = &col->tris[ti];
                    if (fabsf(t->n.y) >= WALKABLE_NY) continue;   /* chao fica com collision_ground */
                    vec3 q = closest_point_tri(*center, t);
                    vec3 d = v3_sub(*center, q);
                    d.y = 0;                                      /* empurra so na horizontal */
                    float dist = v3_len(d);
                    if (dist < radius) {
                        vec3 dir = dist > 1e-5f ? v3_scale(d, 1.0f / dist) : v3_norm(v3(t->n.x, 0, t->n.z));
                        *center = v3_add(*center, v3_scale(dir, radius - dist + 1e-3f));
                        hit = moved = 1;
                    }
                }
            }
        if (!moved) break;
    }
    return hit;
}

static int ray_tri(vec3 o, vec3 d, const ColTri *t, float *out_t) {
    /* Moller-Trumbore, dos dois lados */
    vec3 e1 = v3_sub(t->b, t->a), e2 = v3_sub(t->c, t->a);
    vec3 p = v3_cross(d, e2);
    float det = v3_dot(e1, p);
    if (fabsf(det) < 1e-9f) return 0;
    float inv = 1.0f / det;
    vec3 s = v3_sub(o, t->a);
    float u = v3_dot(s, p) * inv;
    if (u < 0 || u > 1) return 0;
    vec3 q = v3_cross(s, e1);
    float v = v3_dot(d, q) * inv;
    if (v < 0 || u + v > 1) return 0;
    float tt = v3_dot(e2, q) * inv;
    if (tt < 0) return 0;
    *out_t = tt;
    return 1;
}

int collision_raycast(Collision *col, vec3 origin, vec3 dir, float max_dist,
                      float *out_t, vec3 *out_normal) {
    new_stamp(col);
    float best = max_dist;
    int found = 0;
    float step = col->cell_size * 0.5f;
    int last_ci = -1;
    for (float s = 0; s <= max_dist + step && s - step <= best; s += step) {
        vec3 p = v3_add(origin, v3_scale(dir, fminf(s, max_dist)));
        int cx = (int)((p.x - col->origin_x) / col->cell_size);
        int cz = (int)((p.z - col->origin_z) / col->cell_size);
        /* testa a celula e as vizinhas para nao pular quinas */
        for (int dz = -1; dz <= 1; dz++)
            for (int dx = -1; dx <= 1; dx++) {
                int x = cx + dx, z = cz + dz;
                if (x < 0 || z < 0 || x >= col->cells_x || z >= col->cells_z) continue;
                int ci = cell_index(col, x, z);
                if (ci == last_ci) continue;
                for (uint32_t k = col->cell_start[ci]; k < col->cell_start[ci + 1]; k++) {
                    uint32_t ti = col->cell_tris[k];
                    if (col->stamp[ti] == col->stamp_value) continue;
                    col->stamp[ti] = col->stamp_value;
                    float tt;
                    if (ray_tri(origin, dir, &col->tris[ti], &tt) && tt < best) {
                        best = tt;
                        found = 1;
                        if (out_normal) *out_normal = col->tris[ti].n;
                    }
                }
            }
        last_ci = cell_index(col, cx < 0 ? 0 : cx, cz < 0 ? 0 : cz);
    }
    if (found && out_t) *out_t = best;
    return found;
}
