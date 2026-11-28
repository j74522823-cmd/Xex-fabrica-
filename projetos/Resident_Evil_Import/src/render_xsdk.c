/* Renderizador Xenos usando somente a API publica do XSDK. */
#include "render.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "xsdk/gpu.h"
#include "xsdk/texture.h"
#include "re4coop_shaders.h"

static const Map *g_map;
static XsdkShader g_vs, g_ps;
static XsdkTexture *g_textures;
static XsdkTexture g_white;
static XsdkSamplerState g_sampler;
static XsdkDepthStencilState g_depth;
static XsdkBlendState g_blend;
static volatile uint32_t *g_vb, *g_ib, *g_cube_vb, *g_cube_ib;
static uint32_t g_vb_addr, g_ib_addr, g_cube_vb_addr, g_cube_ib_addr;
static uint32_t g_frontbuffer;
static int g_screen_w, g_screen_h;

typedef struct { float view_proj[16], model[16], eye[4]; } VSConstants;
typedef struct { float tint[4], sun_dir[4], fog[4]; } PSConstants;
static VSConstants g_vsc;
static PSConstants g_psc;

static volatile uint32_t *gpu_copy(const void *src, uint32_t bytes, uint32_t *address) {
    volatile uint32_t *memory = xsdk_gpu_alloc(bytes);
    if (!memory) return NULL;
    for (uint32_t i = 0; i < bytes / 4; ++i) {
        uint32_t word;
        memcpy(&word, (const uint8_t *)src + i * 4, 4);
        memory[i] = word;
    }
    *address = xsdk_gpu_address(memory);
    xsdk_gpu_invalidate(*address, bytes);
    return memory;
}

static void build_cube(MapVertex *v, uint32_t *idx) {
    static const float normals[6][3] = {
        {1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1}
    };
    int vi = 0, ii = 0;
    for (int f = 0; f < 6; ++f) {
        const float nx=normals[f][0], ny=normals[f][1], nz=normals[f][2];
        float ux = ny != 0 ? 1.0f : (nz != 0 ? 1.0f : 0.0f);
        float uy = 0.0f, uz = nx != 0 ? 1.0f : 0.0f;
        float wx = ny*uz-nz*uy, wy=nz*ux-nx*uz, wz=nx*uy-ny*ux;
        for (int k=0;k<4;++k) {
            float a=(k==0||k==3)?-0.5f:0.5f, b=k<2?-0.5f:0.5f;
            MapVertex *p=&v[vi+k];
            p->pos[0]=nx*0.5f+ux*a+wx*b; p->pos[1]=ny*0.5f+uy*a+wy*b; p->pos[2]=nz*0.5f+uz*a+wz*b;
            p->normal[0]=nx; p->normal[1]=ny; p->normal[2]=nz;
            p->uv[0]=0.5f; p->uv[1]=0.5f;
        }
        uint32_t base=(uint32_t)vi;
        idx[ii++]=base; idx[ii++]=base+1; idx[ii++]=base+2;
        idx[ii++]=base; idx[ii++]=base+2; idx[ii++]=base+3;
        vi+=4;
    }
}

static int upload_texture(XsdkTexture *texture, const MapTexture *src) {
    NTSTATUS status=xsdk_texture_create(texture, XSDK_FORMAT_A8R8G8B8,
        src->width, src->height, src->levels, true);
    if (!NT_SUCCESS(status)) return 0;
    const uint8_t *pixels=src->data;
    uint32_t w=src->width, h=src->height;
    for (uint32_t level=0; level<src->levels; ++level) {
        xsdk_texture_upload(texture, level, pixels, w*4);
        pixels += w*h*4;
        w=w>1?w/2:1; h=h>1?h/2:1;
    }
    xsdk_gpu_invalidate(texture->address, texture->size_bytes);
    return 1;
}

int render_init(const Map *map, int screen_w, int screen_h) {
    g_map=map; g_screen_w=screen_w; g_screen_h=screen_h;
    NTSTATUS status=xsdk_shader_load(&g_vs, map_vert.container, map_vert.container_bytes);
    if (NT_SUCCESS(status)) status=xsdk_shader_load(&g_ps, map_frag.container, map_frag.container_bytes);
    if (!NT_SUCCESS(status)) return 0;

    const XsdkVertexElement layout[] = {
        {.usage=XSDK_USAGE_POSITION,.format=XSDK_VERTEX_FLOAT3,.stream=0,.offset_bytes=0},
        {.usage=XSDK_USAGE_NORMAL,.format=XSDK_VERTEX_FLOAT3,.stream=0,.offset_bytes=12},
        {.usage=XSDK_USAGE_TEXCOORD,.usage_index=0,.format=XSDK_VERTEX_FLOAT2,.stream=0,.offset_bytes=24}
    };
    const uint32_t strides[]={sizeof(MapVertex)};
    status=xsdk_shader_set_vertex_layout(&g_vs, layout, 3, strides);
    if (!NT_SUCCESS(status)) return 0;

    g_vb=gpu_copy(map->vertices, map->num_vertices*sizeof(MapVertex), &g_vb_addr);
    g_ib=gpu_copy(map->indices, map->num_indices*sizeof(uint32_t), &g_ib_addr);
    if (!g_vb || !g_ib) return 0;

    MapVertex cube_v[24]; uint32_t cube_i[36];
    build_cube(cube_v,cube_i);
    g_cube_vb=gpu_copy(cube_v,sizeof cube_v,&g_cube_vb_addr);
    g_cube_ib=gpu_copy(cube_i,sizeof cube_i,&g_cube_ib_addr);
    if (!g_cube_vb || !g_cube_ib) return 0;

    if (map->num_textures) {
        g_textures=(XsdkTexture *)calloc(map->num_textures,sizeof *g_textures);
        if (!g_textures) return 0;
        for (uint32_t i=0;i<map->num_textures;++i)
            if (!upload_texture(&g_textures[i],&map->textures[i])) return 0;
    }

    static uint32_t white_pixels[16];
    for (unsigned i=0;i<16;++i) white_pixels[i]=0xFFFFFFFFu;
    status=xsdk_texture_create(&g_white,XSDK_FORMAT_A8R8G8B8,4,4,1,true);
    if (!NT_SUCCESS(status)) return 0;
    xsdk_texture_upload(&g_white,0,white_pixels,4*4);
    xsdk_gpu_invalidate(g_white.address,g_white.size_bytes);

    const XsdkSampler sampler={
        .mag_filter=XSDK_FILTER_LINEAR,.min_filter=XSDK_FILTER_LINEAR,
        .mip_filter=XSDK_FILTER_LINEAR,.address_u=XSDK_ADDRESS_WRAP,
        .address_v=XSDK_ADDRESS_WRAP,.max_anisotropy=4
    };
    xsdk_texture_sampler_state(&g_sampler,&sampler);

    const XsdkDepthStencil depth={.depth_test=true,.depth_write=true,
        .depth_compare=XSDK_COMPARE_LESS_EQUAL};
    xsdk_gpu_depth_stencil_state(&g_depth,&depth);
    const XsdkBlend blend={.color_source=XSDK_BLEND_ONE,.color_dest=XSDK_BLEND_ZERO,
        .color_op=XSDK_BLEND_OP_ADD,.alpha_source=XSDK_BLEND_ONE,.alpha_dest=XSDK_BLEND_ZERO,
        .alpha_op=XSDK_BLEND_OP_ADD,.write_mask=XSDK_WRITE_ALL};
    xsdk_gpu_blend_state(&g_blend,&blend);

    float sx=0.45f,sy=0.75f,sz=0.35f,sl=sqrtf(sx*sx+sy*sy+sz*sz);
    g_psc.sun_dir[0]=sx/sl; g_psc.sun_dir[1]=sy/sl; g_psc.sun_dir[2]=sz/sl;
    g_psc.fog[0]=0.46f; g_psc.fog[1]=0.44f; g_psc.fog[2]=0.40f; g_psc.fog[3]=0.018f;
    return 1;
}

void render_shutdown(void) {
    if (g_textures) {
        for (uint32_t i=0;i<g_map->num_textures;++i) xsdk_texture_free(&g_textures[i]);
        free(g_textures); g_textures=NULL;
    }
    xsdk_texture_free(&g_white);
    if (g_cube_ib) xsdk_gpu_free(g_cube_ib);
    if (g_cube_vb) xsdk_gpu_free(g_cube_vb);
    if (g_ib) xsdk_gpu_free(g_ib);
    if (g_vb) xsdk_gpu_free(g_vb);
    xsdk_shader_free(&g_ps); xsdk_shader_free(&g_vs);
    g_cube_ib=g_cube_vb=g_ib=g_vb=NULL;
}

void render_frame_begin(void) {
    if (!NT_SUCCESS(xsdk_present_begin(&g_frontbuffer,5000))) return;
    xsdk_gpu_set_target((uint32_t)g_screen_w,(uint32_t)g_screen_h);
    xsdk_gpu_set_depth_stencil(&g_depth);
    xsdk_gpu_set_blend(&g_blend);
    xsdk_gpu_set_shaders(&g_vs,&g_ps);
    xsdk_built_shader_set_literals(&map_vert);
    xsdk_built_shader_set_literals(&map_frag);
}

void render_view_begin(int x,int y,int w,int h,const mat4 *view_proj,vec3 eye) {
    xsdk_gpu_set_viewport((float)x,(float)y,(float)w,(float)h,0.0f,1.0f);
    memcpy(g_vsc.view_proj,view_proj->m,sizeof g_vsc.view_proj);
    g_vsc.eye[0]=eye.x; g_vsc.eye[1]=eye.y; g_vsc.eye[2]=eye.z; g_vsc.eye[3]=1.0f;
}

static void set_constants(void) {
    xsdk_gpu_set_vertex_constants(MAP_VERT_UNIFORM_0_0,g_vsc.view_proj,
        MAP_VERT_UNIFORM_0_0_REGISTERS);
    xsdk_gpu_set_pixel_constants(MAP_FRAG_UNIFORM_0_2,g_psc.tint,
        MAP_FRAG_UNIFORM_0_2_REGISTERS);
}

void render_map(void) {
    mat4 identity=m4_identity();
    memcpy(g_vsc.model,identity.m,sizeof g_vsc.model);
    g_psc.tint[0]=g_psc.tint[1]=g_psc.tint[2]=g_psc.tint[3]=1.0f;
    set_constants();
    xsdk_gpu_set_vertices(0,g_vb_addr,g_map->num_vertices*sizeof(MapVertex));
    for (uint32_t i=0;i<g_map->num_batches;++i) {
        const MapBatch *batch=&g_map->batches[i];
        if (batch->texture>=g_map->num_textures) continue;
        xsdk_gpu_set_texture(MAP_FRAG_SAMPLER_0_1,&g_textures[batch->texture],&g_sampler);
        uint32_t left=batch->index_count, offset=batch->first_index;
        while (left) {
            uint32_t count=left>65535u?65535u:left;
            count-=count%3u;
            if (!count) break;
            xsdk_gpu_draw_indexed(XSDK_PRIMITIVE_TRIANGLE_LIST,g_ib_addr+offset*4,count,true);
            offset+=count; left-=count;
        }
    }
}

void render_box(const mat4 *model,vec3 color) {
    memcpy(g_vsc.model,model->m,sizeof g_vsc.model);
    g_psc.tint[0]=color.x; g_psc.tint[1]=color.y; g_psc.tint[2]=color.z; g_psc.tint[3]=1.0f;
    set_constants();
    xsdk_gpu_set_texture(MAP_FRAG_SAMPLER_0_1,&g_white,&g_sampler);
    xsdk_gpu_set_vertices(0,g_cube_vb_addr,24*sizeof(MapVertex));
    xsdk_gpu_draw_indexed(XSDK_PRIMITIVE_TRIANGLE_LIST,g_cube_ib_addr,36,true);
}

void render_text(int x,int y,float scale,uint32_t argb,const char *text) {
    (void)x; (void)y; (void)scale; (void)argb; (void)text;
}

void render_frame_end(void) {
    xsdk_gpu_resolve(g_frontbuffer,(uint32_t)g_screen_w,(uint32_t)g_screen_h,0xFF75706A);
    xsdk_present_end();
}
