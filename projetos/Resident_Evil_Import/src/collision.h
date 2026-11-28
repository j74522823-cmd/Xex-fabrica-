/* collision.h - colisao usando a propria malha do mapa (grade uniforme no plano XZ). */
#ifndef COLLISION_H
#define COLLISION_H

#include <stdint.h>
#include "map.h"

typedef struct {
    vec3 a, b, c;
    vec3 n;                      /* normal da face */
} ColTri;

typedef struct {
    ColTri *tris;
    uint32_t num_tris;
    uint32_t *cell_start;        /* num_cells + 1 */
    uint32_t *cell_tris;
    uint32_t *stamp;             /* evita testar o mesmo triangulo duas vezes */
    uint32_t stamp_value;
    int cells_x, cells_z;
    float cell_size;
    float origin_x, origin_z;
    vec3 bounds_min, bounds_max;
} Collision;

void collision_build(Collision *col, const Map *map, float cell_size);
void collision_free(Collision *col);

/* Chao mais alto em (x, z) entre y_top e y_bottom. Retorna 1 se achou. */
int collision_ground(Collision *col, float x, float z, float y_top, float y_bottom,
                     float *out_y, vec3 *out_normal);

/* Empurra uma esfera para fora das paredes (so no plano horizontal). Retorna 1 se encostou. */
int collision_push_sphere(Collision *col, vec3 *center, float radius);

/* Raio contra o mapa. Retorna 1 e a distancia se acertou antes de max_dist. */
int collision_raycast(Collision *col, vec3 origin, vec3 dir, float max_dist,
                      float *out_t, vec3 *out_normal);

#endif
