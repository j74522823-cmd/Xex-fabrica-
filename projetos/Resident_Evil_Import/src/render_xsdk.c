/* render_xsdk.c - implementacao de render.h em cima do xsdk (Xbox 360).
 *
 * IMPORTANTE: os nomes das FUNCOES abaixo vem da documentacao do xsdk (docs/GUIDE.md).
 * Os nomes de TIPOS, campos de struct e valores de enum foram deduzidos e estao marcados
 * com "XSDK:". Confira cada um contra include/xsdk/gpu.h e o sample do cubo em samples/
 * (ele usa os mesmos passos: shader GLSL, vertex layout, constantes, textura, draw indexado).
 */
#include "render.h"

#include <string.h>
#include <stdlib.h>

#include "xsdk/gpu.h"

/* XSDK: xsdk_add_shaders(re4coop shaders/map.vert shaders/map.frag) gera os shaders
   compilados. Ajuste os nomes abaixo ao que o CMake gerar (veja o sample do cubo). */
#include "map_vert.h"   /* XSDK: esperado: map_vert[] e map_vert_size */
#include "map_frag.h"   /* XSDK: esperado: map_frag[] e map_frag_size */

typedef struct {
    float view_proj[16];
    float model[16];
    float eye[4];
} VSConstants;

typedef struct {
    float tint[4];
    float sun_dir[4];
    float fog[4];
} PSConstants;

static const Map *g_map;
static int g_screen_w, g_screen_h;

static XsdkShader g_vs, g_ps;                 /* XSDK: tipo do shader */
static XsdkTexture *g_textures;               /* XSDK: tipo da textura */
static XsdkTexture g_white;
static XsdkSamplerState g_sampler;            /* XSDK: estado do sampler */

static void *g_vb, *g_ib;                     /* memoria de GPU do mapa */
static uint32_t g_vb_addr, g_ib_addr;
static void *g_cube_vb, *g_cube_ib;
static uint32_t g_cube_vb_addr, g_cube_ib_addr;

static VSConstants g_vsc;
static PSConstants g_psc;
static uint32_t g_frontbuffer;

/* ---- cubo unitario (24 vertices, normais por face) ---- */
static void build_cube(MapVertex *v, uint32_t *idx) {
    static const float n[6][3] = {{1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1}};
    int vi = 0, ii = 0;
    for (int f = 0; f < 6; f++) {
        float nx = n[f][0], ny = n[f][1], nz = n[f][2];
        /* dois eixos tangentes da face */
        float ux = ny != 0 ? 1 : (nz != 0 ? 1 : 0), uy = 0, uz = nx != 0 ? 1 : 0;
        float wx = ny * uz - nz * uy, wy = nz * ux - nx * uz, wz = nx * uy - ny * ux;
        for (int k = 0; k < 4; k++) {
            float a = (k == 0 || k == 3) ? -0.5f : 0.5f, b = (k < 2) ? -0.5f : 0.5f;
            MapVertex *p = &v[vi + k];
            p->pos[0] = nx * 0.5f + ux * a + wx * b;
            p->pos[1] = ny * 0.5f + uy * a + wy * b;
            p->pos[2] = nz * 0.5f + uz * a + wz * b;
            p->normal[0] = nx; p->normal[1] = ny; p->normal[2] = nz;
            p->uv[0] = 0.5f; p->uv[1] = 0.5f;
        }
        uint32_t base = (uint32_t)vi;
        idx[ii++] = base; idx[ii++] = base + 1; idx[ii++] = base + 2;
        idx[ii++] = base; idx[ii++] = base + 2; idx[ii++] = base + 3;
        vi += 4;
    }
}

static void upload_texture(XsdkTexture *tex, const MapTexture *src) {
    /* XSDK: formato ARGB8 linear; o enum pode se chamar XSDK_FORMAT_8_8_8_8 ou parecido */
    xsdk_texture_create(tex, XSDK_FORMAT_8_8_8_8, src->width, src->height, src->levels, 0);
    const uint8_t *p = src->data;
    uint32_t w = src->width, h = src->height;
    for (uint32_t level = 0; level < src->levels; level++) {
        xsdk_texture_upload(tex, level, p, w * 4);
        p += w * h * 4;
        w = w > 1 ? w / 2 : 1;
        h = h > 1 ? h / 2 : 1;
    }
}

static void *gpu_copy(const void *src, uint32_t bytes, uint32_t *addr) {
    void *mem = xsdk_gpu_alloc(bytes);
    memcpy(mem, src, bytes);
    *addr = xsdk_gpu_address(mem);
    xsdk_gpu_invalidate(*addr, bytes);
    return mem;
}

int render_init(const Map *map, int screen_w, int screen_h) {
    g_map = map;
    g_screen_w = screen_w;
    g_screen_h = screen_h;

    if (!xsdk_shader_load(&g_vs, map_vert, map_vert_size)) return 0;
    if (!xsdk_shader_load(&g_ps, map_frag, map_frag_size)) return 0;

    /* XSDK: layout do vertice (32 bytes): pos float3 @0, normal float3 @12, uv float2 @24.
       Confira o nome da struct e dos campos no gpu.h. */
    XsdkVertexElement elements[3] = {
        {.stream = 0, .offset = 0,  .format = XSDK_VERTEX_FLOAT3},
        {.stream = 0, .offset = 12, .format = XSDK_VERTEX_FLOAT3},
        {.stream = 0, .offset = 24, .format = XSDK_VERTEX_FLOAT2},
    };
    uint32_t strides[1] = {sizeof(MapVertex)};
    xsdk_shader_set_vertex_layout(&g_vs, elements, 3, strides);

    g_vb = gpu_copy(map->vertices, map->num_vertices * sizeof(MapVertex), &g_vb_addr);
    g_ib = gpu_copy(map->indices, map->num_indices * sizeof(uint32_t), &g_ib_addr);

    MapVertex cube_v[24];
    uint32_t cube_i[36];
    build_cube(cube_v, cube_i);
    g_cube_vb = gpu_copy(cube_v, sizeof cube_v, &g_cube_vb_addr);
    g_cube_ib = gpu_copy(cube_i, sizeof cube_i, &g_cube_ib_addr);

    g_textures = (XsdkTexture *)calloc(map->num_textures, sizeof(XsdkTexture));
    for (uint32_t i = 0; i < map->num_textures; i++) upload_texture(&g_textures[i], &map->textures[i]);

    static uint8_t white[4 * 4 * 4];
    memset(white, 0xFF, sizeof white);
    MapTexture wt = {4, 4, 1, white, sizeof white};
    upload_texture(&g_white, &wt);

    /* XSDK: sampler com filtro trilinear e repeticao (wrap) */
    XsdkSampler sampler_desc = {
        .filter = XSDK_FILTER_LINEAR,
        .mip_filter = XSDK_FILTER_LINEAR,
        .address_u = XSDK_ADDRESS_WRAP,
        .address_v = XSDK_ADDRESS_WRAP,
        .max_anisotropy = 4,
    };
    xsdk_texture_sampler_state(&g_sampler, &sampler_desc);

    /* luz e neblina (tom de fim de tarde) */
    float sx = 0.45f, sy = 0.75f, sz = 0.35f, sl = sqrtf(sx * sx + sy * sy + sz * sz);
    g_psc.sun_dir[0] = sx / sl; g_psc.sun_dir[1] = sy / sl; g_psc.sun_dir[2] = sz / sl;
    g_psc.fog[0] = 0.46f; g_psc.fog[1] = 0.44f; g_psc.fog[2] = 0.40f; g_psc.fog[3] = 0.018f;
    return 1;
}

void render_shutdown(void) {
    free(g_textures);
}

void render_frame_begin(void) {
    xsdk_present_begin(&g_frontbuffer, 100);
    xsdk_gpu_set_target(g_screen_w, g_screen_h);

    /* XSDK: profundidade ligada, teste "menor ou igual", escrita ligada */
    XsdkDepthStencilState ds = {.depth_test = 1, .depth_write = 1, .depth_func = XSDK_CMP_LESS_EQUAL};
    xsdk_gpu_set_depth_stencil(&ds);
    XsdkBlendState blend = {.enable = 0};
    xsdk_gpu_set_blend(&blend);
    xsdk_gpu_set_shaders(&g_vs, &g_ps);
}

void render_view_begin(int x, int y, int w, int h, const mat4 *view_proj, vec3 eye) {
    /* XSDK: viewport em pixels; o README diz que o gpu.h tem viewports. Ajuste o nome. */
    xsdk_gpu_set_viewport(x, y, w, h, 0.0f, 1.0f);
    memcpy(g_vsc.view_proj, view_proj->m, sizeof g_vsc.view_proj);
    g_vsc.eye[0] = eye.x; g_vsc.eye[1] = eye.y; g_vsc.eye[2] = eye.z; g_vsc.eye[3] = 1;
}

static void set_constants(void) {
    /* XSDK: se o xsdk preferir constantes por nome, troque por xsdk_shader_constant(&g_vs, "ViewProj", ...) */
    xsdk_gpu_set_vertex_constants(0, (const float *)&g_vsc, sizeof g_vsc / 16);
    xsdk_gpu_set_pixel_constants(0, (const float *)&g_psc, sizeof g_psc / 16);
}

void render_map(void) {
    mat4 id = m4_identity();
    memcpy(g_vsc.model, id.m, sizeof g_vsc.model);
    g_psc.tint[0] = g_psc.tint[1] = g_psc.tint[2] = g_psc.tint[3] = 1;
    set_constants();
    xsdk_gpu_set_vertices(0, g_vb_addr, g_map->num_vertices * sizeof(MapVertex));
    for (uint32_t i = 0; i < g_map->num_batches; i++) {
        const MapBatch *b = &g_map->batches[i];
        xsdk_gpu_set_texture(0, &g_textures[b->texture], &g_sampler);
        /* XSDK: primitiva lista de triangulos; indices de 32 bits */
        xsdk_gpu_draw_indexed(XSDK_PRIM_TRIANGLE_LIST, g_ib_addr + b->first_index * 4, b->index_count, 1);
    }
}

void render_box(const mat4 *model, vec3 color) {
    memcpy(g_vsc.model, model->m, sizeof g_vsc.model);
    g_psc.tint[0] = color.x; g_psc.tint[1] = color.y; g_psc.tint[2] = color.z; g_psc.tint[3] = 1;
    set_constants();
    xsdk_gpu_set_texture(0, &g_white, &g_sampler);
    xsdk_gpu_set_vertices(0, g_cube_vb_addr, 24 * sizeof(MapVertex));
    xsdk_gpu_draw_indexed(XSDK_PRIM_TRIANGLE_LIST, g_cube_ib_addr, 36, 1);
}

void render_text(int x, int y, float scale, uint32_t argb, const char *text) {
    xsdk_text_draw(x, y, scale, argb, text);
}

void render_frame_end(void) {
    /* copia o eDRAM para o frontbuffer e limpa para o proximo quadro com a cor da neblina */
    xsdk_gpu_resolve(g_frontbuffer, g_screen_w, g_screen_h, 0xFF75706A);
    xsdk_present_end();
}
