/* map.c - leitura do .rfm (big-endian). Funciona no 360 (big-endian) e no PC (little-endian). */
#include "map.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint32_t be32(const uint8_t *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}
static uint16_t be16(const uint8_t *p) { return (uint16_t)((p[0] << 8) | p[1]); }
static float bef(const uint8_t *p) {
    uint32_t u = be32(p);
    float f;
    memcpy(&f, &u, 4);
    return f;
}

int map_load(Map *map, const char *path) {
    memset(map, 0, sizeof *map);
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *d = (uint8_t *)malloc((size_t)size);
    if (!d || fread(d, 1, (size_t)size, f) != (size_t)size) {
        fclose(f);
        free(d);
        return 0;
    }
    fclose(f);
    if (size < 64 || memcmp(d, "RFM1", 4) != 0 || be32(d + 4) != 1) {
        free(d);
        return 0;
    }
    map->file = d;
    map->num_textures = be32(d + 8);
    map->num_batches = be32(d + 12);
    map->num_vertices = be32(d + 16);
    map->num_indices = be32(d + 20);
    map->bounds_min = v3(bef(d + 24), bef(d + 28), bef(d + 32));
    map->bounds_max = v3(bef(d + 36), bef(d + 40), bef(d + 44));

    const uint8_t *p = d + 64;
    map->textures = (MapTexture *)calloc(map->num_textures, sizeof(MapTexture));
    for (uint32_t i = 0; i < map->num_textures; i++, p += 16) {
        MapTexture *t = &map->textures[i];
        t->width = be16(p);
        t->height = be16(p + 2);
        t->levels = be16(p + 4);
        t->data = d + be32(p + 8);
        t->size = be32(p + 12);
    }
    map->batches = (MapBatch *)calloc(map->num_batches, sizeof(MapBatch));
    for (uint32_t i = 0; i < map->num_batches; i++, p += 16) {
        map->batches[i].texture = be32(p);
        map->batches[i].first_index = be32(p + 4);
        map->batches[i].index_count = be32(p + 8);
        map->batches[i].flags = be32(p + 12);
    }

    /* Vertices e indices: converte no lugar para a ordem de bytes da maquina.
       No 360 (big-endian) a troca nao faz nada. */
    map->vertices = (MapVertex *)p;
    uint32_t nfloats = map->num_vertices * 8;
    for (uint32_t i = 0; i < nfloats; i++) {
        float v = bef(p + i * 4);
        memcpy((uint8_t *)p + i * 4, &v, 4);
    }
    p += map->num_vertices * sizeof(MapVertex);
    map->indices = (uint32_t *)p;
    for (uint32_t i = 0; i < map->num_indices; i++) {
        uint32_t v = be32(p + i * 4);
        memcpy((uint8_t *)p + i * 4, &v, 4);
    }
    return 1;
}

void map_free(Map *map) {
    free(map->textures);
    free(map->batches);
    free(map->file);
    memset(map, 0, sizeof *map);
}
