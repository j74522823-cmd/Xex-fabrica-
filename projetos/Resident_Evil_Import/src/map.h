/* map.h - carrega o mapa .rfm gerado por tools/convert_map.py */
#ifndef MAP_H
#define MAP_H

#include <stdint.h>
#include "vmath.h"

typedef struct {
    float pos[3];
    float normal[3];
    float uv[2];
} MapVertex;                     /* 32 bytes, igual ao layout do shader */

typedef struct {
    uint16_t width, height, levels;
    const uint8_t *data;         /* ARGB8, nivel 0 seguido dos mips */
    uint32_t size;
} MapTexture;

typedef struct {
    uint32_t texture;
    uint32_t first_index;
    uint32_t index_count;
    uint32_t flags;
} MapBatch;

typedef struct {
    uint8_t *file;               /* arquivo inteiro na memoria */
    uint32_t num_textures, num_batches, num_vertices, num_indices;
    MapTexture *textures;
    MapBatch *batches;
    MapVertex *vertices;         /* ja na ordem de bytes da maquina */
    uint32_t *indices;
    vec3 bounds_min, bounds_max;
} Map;

int  map_load(Map *map, const char *path);   /* 1 = ok */
void map_free(Map *map);

#endif
