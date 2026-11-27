// Procedural two-player 3D house test for Xbox 360 / XSDK.
// The room and characters are generated from simple box meshes; no external assets are required.

#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "house_shaders.h"
#include "xsdk/gpu.h"
#include "xsdk/kernel.h"
#include "xsdk/log.h"
#include "xsdk/present.h"
#include "xsdk/shader.h"
#include "xsdk/splash.h"

enum {
    SPLASH_MS = 1800,
    BUFFERS = 2,
    SWAP_INTERVAL = 1,
    BEGIN_TIMEOUT_MS = 5000,
    VERTEX_FLOATS = 6,
    STRIDE_BYTES = VERTEX_FLOATS * 4,
    VERTEX_COUNT = 24,
    INDEX_COUNT = 36,
    VERTEX_BYTES = VERTEX_COUNT * STRIDE_BYTES,
    INDEX_BYTES = INDEX_COUNT * 2,
};

static const float DEAD_ZONE = 8000.0f;
static const float MOVE_SPEED = 0.075f;
static const float NEAR_PLANE = 0.1f;
static const float FAR_PLANE = 60.0f;
static const float FOV = 0.92f;

typedef struct { float m[16]; } Matrix;
typedef struct { float x, y, z; } Vec3;

typedef struct {
    XsdkShader vertex;
    XsdkShader pixel;
    XsdkDepthStencilState depth;
    volatile uint32_t *vertices;
    volatile uint32_t *indices;
} Scene;

typedef struct {
    float x;
    float z;
    float r, g, b;
} Player;

static const XsdkVertexElement vertex_layout[] = {
    { .usage = XSDK_USAGE_POSITION, .format = XSDK_VERTEX_FLOAT3, .offset_bytes = 0 },
    { .usage = XSDK_USAGE_COLOR, .format = XSDK_VERTEX_FLOAT3, .offset_bytes = 12 },
};

static const float face_dirs[6][3][3] = {
    {{ 1, 0, 0}, { 0, 0,-1}, { 0, 1, 0}},
    {{-1, 0, 0}, { 0, 0, 1}, { 0, 1, 0}},
    {{ 0, 1, 0}, { 1, 0, 0}, { 0, 0,-1}},
    {{ 0,-1, 0}, { 1, 0, 0}, { 0, 0, 1}},
    {{ 0, 0, 1}, { 1, 0, 0}, { 0, 1, 0}},
    {{ 0, 0,-1}, {-1, 0, 0}, { 0, 1, 0}},
};

static const float face_colors[6][3] = {
    {0.78f, 0.82f, 0.90f}, {0.62f, 0.68f, 0.78f},
    {0.88f, 0.90f, 0.96f}, {0.40f, 0.45f, 0.54f},
    {0.72f, 0.78f, 0.88f}, {0.56f, 0.62f, 0.72f},
};

static void write_gpu(volatile uint32_t *memory, const void *data, uint32_t size_bytes)
{
    for (uint32_t i = 0; i < size_bytes / 4; ++i) {
        uint32_t word;
        memcpy(&word, (const uint8_t *)data + i * 4, 4);
        memory[i] = word;
    }
    xsdk_gpu_invalidate(xsdk_gpu_address(memory), size_bytes);
}

static bool make_cube_mesh(Scene *scene)
{
    float vertices[VERTEX_COUNT][VERTEX_FLOATS];
    uint16_t indices[INDEX_COUNT];

    for (uint32_t face = 0; face < 6; ++face) {
        for (uint32_t corner = 0; corner < 4; ++corner) {
            const float across = (corner & 1) ? 1.0f : -1.0f;
            const float up = (corner & 2) ? 1.0f : -1.0f;
            float *v = vertices[face * 4 + corner];
            for (uint32_t axis = 0; axis < 3; ++axis)
                v[axis] = 0.5f * (face_dirs[face][0][axis] +
                    across * face_dirs[face][1][axis] + up * face_dirs[face][2][axis]);
            v[3] = face_colors[face][0];
            v[4] = face_colors[face][1];
            v[5] = face_colors[face][2];
        }
        const uint16_t base = (uint16_t)(face * 4);
        const uint16_t quad[6] = {base, (uint16_t)(base + 1), (uint16_t)(base + 2),
                                  (uint16_t)(base + 2), (uint16_t)(base + 1), (uint16_t)(base + 3)};
        memcpy(&indices[face * 6], quad, sizeof(quad));
    }

    scene->vertices = xsdk_gpu_alloc(VERTEX_BYTES);
    scene->indices = xsdk_gpu_alloc(INDEX_BYTES);
    if (!scene->vertices || !scene->indices) {
        xsdk_log_write("house: GPU mesh allocation failed");
        return false;
    }
    write_gpu(scene->vertices, vertices, sizeof(vertices));
    write_gpu(scene->indices, indices, sizeof(indices));
    return true;
}

static Matrix multiply(const Matrix *a, const Matrix *b)
{
    Matrix out;
    for (uint32_t c = 0; c < 4; ++c)
        for (uint32_t r = 0; r < 4; ++r) {
            float sum = 0.0f;
            for (uint32_t k = 0; k < 4; ++k)
                sum += a->m[k * 4 + r] * b->m[c * 4 + k];
            out.m[c * 4 + r] = sum;
        }
    return out;
}

static Vec3 normalize(Vec3 v)
{
    const float length = sqrtf(v.x * v.x + v.y * v.y + v.z * v.z);
    if (length < 0.0001f) return (Vec3){0, 0, 0};
    return (Vec3){v.x / length, v.y / length, v.z / length};
}

static Vec3 subtract(Vec3 a, Vec3 b)
{
    return (Vec3){a.x - b.x, a.y - b.y, a.z - b.z};
}

static Vec3 cross(Vec3 a, Vec3 b)
{
    return (Vec3){a.y * b.z - a.z * b.y,
                  a.z * b.x - a.x * b.z,
                  a.x * b.y - a.y * b.x};
}

static float dot(Vec3 a, Vec3 b)
{
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

static Matrix perspective(float aspect)
{
    const float f = 1.0f / tanf(FOV * 0.5f);
    const float fz = FAR_PLANE / (NEAR_PLANE - FAR_PLANE);
    Matrix m = {{0}};
    m.m[0] = f / aspect;
    m.m[5] = f;
    m.m[10] = fz;
    m.m[11] = -1.0f;
    m.m[14] = NEAR_PLANE * fz;
    return m;
}

static Matrix look_at(Vec3 eye, Vec3 target, Vec3 up)
{
    const Vec3 f = normalize(subtract(target, eye));
    const Vec3 s = normalize(cross(f, up));
    const Vec3 u = cross(s, f);
    Matrix m = {{
        s.x, u.x, -f.x, 0,
        s.y, u.y, -f.y, 0,
        s.z, u.z, -f.z, 0,
        -dot(s, eye), -dot(u, eye), dot(f, eye), 1
    }};
    return m;
}

static Matrix model_matrix(float x, float y, float z, float sx, float sy, float sz)
{
    Matrix m = {{
        sx, 0,  0,  0,
        0,  sy, 0,  0,
        0,  0,  sz, 0,
        x,  y,  z,  1
    }};
    return m;
}

static void draw_box(const Scene *scene, const Matrix *view_projection,
                     float x, float y, float z, float sx, float sy, float sz)
{
    const Matrix model = model_matrix(x, y, z, sx, sy, sz);
    const Matrix mvp = multiply(view_projection, &model);
    xsdk_gpu_set_vertex_constants(HOUSE_VERT_PUSH, mvp.m, HOUSE_VERT_PUSH_REGISTERS);
    xsdk_gpu_draw_indexed(XSDK_PRIMITIVE_TRIANGLE_LIST,
        xsdk_gpu_address(scene->indices), INDEX_COUNT, false);
}

static void draw_player(const Scene *scene, const Matrix *vp, const Player *p)
{
    // A deliberately simple articulated-looking mannequin made from boxes.
    draw_box(scene, vp, p->x, 1.16f, p->z, 0.62f, 0.82f, 0.38f);
    draw_box(scene, vp, p->x, 1.82f, p->z, 0.43f, 0.43f, 0.43f);
    draw_box(scene, vp, p->x - 0.43f, 1.18f, p->z, 0.18f, 0.72f, 0.20f);
    draw_box(scene, vp, p->x + 0.43f, 1.18f, p->z, 0.18f, 0.72f, 0.20f);
    draw_box(scene, vp, p->x - 0.17f, 0.43f, p->z, 0.22f, 0.72f, 0.25f);
    draw_box(scene, vp, p->x + 0.17f, 0.43f, p->z, 0.22f, 0.72f, 0.25f);
}

static float axis_value(int16_t value)
{
    const float v = (float)value;
    return (v > DEAD_ZONE || v < -DEAD_ZONE) ? v / 32768.0f : 0.0f;
}

static void update_player(Player *p, const INPUT_STATE *input)
{
    p->x += axis_value(input->gamepad.thumb_lx) * MOVE_SPEED;
    p->z -= axis_value(input->gamepad.thumb_ly) * MOVE_SPEED;
    if (p->x < -3.2f) p->x = -3.2f;
    if (p->x >  3.2f) p->x =  3.2f;
    if (p->z < -2.9f) p->z = -2.9f;
    if (p->z >  2.9f) p->z =  2.9f;
}

static void render_scene(const Scene *scene, uint32_t address, uint32_t width, uint32_t height,
                         const Player *p1, const Player *p2)
{
    const Matrix projection = perspective((float)width / (float)height);
    const Matrix view = look_at((Vec3){0.0f, 5.3f, 9.5f},
                                (Vec3){0.0f, 1.0f, 0.0f},
                                (Vec3){0.0f, 1.0f, 0.0f});
    const Matrix vp = multiply(&projection, &view);

    xsdk_gpu_set_target(width, height);
    xsdk_gpu_set_depth_stencil(&scene->depth);
    xsdk_gpu_set_shaders(&scene->vertex, &scene->pixel);
    xsdk_built_shader_set_literals(&house_vert);
    xsdk_built_shader_set_literals(&house_frag);
    xsdk_gpu_set_vertices(0, xsdk_gpu_address(scene->vertices), VERTEX_BYTES);

    // Open-front room: floor, rear wall and two side walls.
    draw_box(scene, &vp, 0.0f, -0.12f, 0.0f, 8.0f, 0.24f, 8.0f);
    draw_box(scene, &vp, 0.0f, 1.95f, -3.9f, 8.0f, 4.0f, 0.20f);
    draw_box(scene, &vp, -3.9f, 1.95f, 0.0f, 0.20f, 4.0f, 8.0f);
    draw_box(scene, &vp,  3.9f, 1.95f, 0.0f, 0.20f, 4.0f, 8.0f);

    // Player 1: blue-green; Player 2: warm orange. The separate positions are controlled independently.
    draw_player(scene, &vp, p1);
    draw_player(scene, &vp, p2);

    xsdk_gpu_resolve(address, width, height, 0xFF101820);
}

static bool create_scene(Scene *scene)
{
    NTSTATUS status = xsdk_shader_load(&scene->vertex, house_vert.container, house_vert.container_bytes);
    if (!NT_SUCCESS(status)) {
        xsdk_log_write("house: vertex shader load failed 0x%08X", (unsigned)status);
        return false;
    }
    status = xsdk_shader_load(&scene->pixel, house_frag.container, house_frag.container_bytes);
    if (!NT_SUCCESS(status)) {
        xsdk_log_write("house: pixel shader load failed 0x%08X", (unsigned)status);
        xsdk_shader_free(&scene->vertex);
        return false;
    }
    const uint32_t strides[1] = {STRIDE_BYTES};
    status = xsdk_shader_set_vertex_layout(&scene->vertex, vertex_layout,
        sizeof(vertex_layout) / sizeof(vertex_layout[0]), strides);
    if (!NT_SUCCESS(status)) {
        xsdk_log_write("house: vertex layout failed 0x%08X", (unsigned)status);
        xsdk_shader_free(&scene->pixel);
        xsdk_shader_free(&scene->vertex);
        return false;
    }

    const XsdkDepthStencil depth = {
        .depth_test = true,
        .depth_write = true,
        .depth_compare = XSDK_COMPARE_LESS_EQUAL,
    };
    xsdk_gpu_depth_stencil_state(&scene->depth, &depth);

    if (!make_cube_mesh(scene)) {
        if (scene->indices) xsdk_gpu_free(scene->indices);
        if (scene->vertices) xsdk_gpu_free(scene->vertices);
        xsdk_shader_free(&scene->pixel);
        xsdk_shader_free(&scene->vertex);
        return false;
    }
    return true;
}

static void destroy_scene(Scene *scene)
{
    (void)xsdk_gpu_wait(xsdk_gpu_fence(), 1000);
    if (scene->indices) xsdk_gpu_free(scene->indices);
    if (scene->vertices) xsdk_gpu_free(scene->vertices);
    xsdk_shader_free(&scene->pixel);
    xsdk_shader_free(&scene->vertex);
}

int main(void)
{
    xsdk_log_write("house: two-player procedural 3D test starting");
    const NTSTATUS splash = xsdk_splash_show(SPLASH_MS);
    if (!NT_SUCCESS(splash))
        xsdk_log_write("house: splash returned 0x%08X", (unsigned)splash);

    NTSTATUS status = xsdk_gpu_open();
    if (!NT_SUCCESS(status)) {
        xsdk_log_write("house: GPU open failed 0x%08X", (unsigned)status);
        return 1;
    }

    Scene scene = {0};
    if (!create_scene(&scene)) {
        (void)xsdk_gpu_close();
        return 1;
    }

    uint32_t width = 0, height = 0;
    status = xsdk_present_open(XSDK_DISPLAY_720P, BUFFERS, SWAP_INTERVAL, &width, &height);
    if (!NT_SUCCESS(status)) {
        xsdk_log_write("house: display open failed 0x%08X", (unsigned)status);
        destroy_scene(&scene);
        (void)xsdk_gpu_close();
        return 1;
    }
    xsdk_log_write("house: running at %ux%u; left sticks control each player; BACK exits",
        (unsigned)width, (unsigned)height);

    Player p1 = {-1.25f, 1.0f, 0.18f, 0.82f, 0.92f};
    Player p2 = { 1.25f, 1.0f, 1.00f, 0.52f, 0.16f};
    bool running = true;
    while (running) {
        INPUT_STATE input1 = {0};
        INPUT_STATE input2 = {0};
        if (XamInputGetState(0, 0, &input1) == ERROR_SUCCESS) {
            if (input1.gamepad.buttons & INPUT_GAMEPAD_BACK) running = false;
            update_player(&p1, &input1);
        }
        if (XamInputGetState(1, 0, &input2) == ERROR_SUCCESS)
            update_player(&p2, &input2);

        uint32_t address = 0;
        status = xsdk_present_begin(&address, BEGIN_TIMEOUT_MS);
        if (!NT_SUCCESS(status)) {
            xsdk_log_write("house: present begin failed 0x%08X", (unsigned)status);
            break;
        }
        render_scene(&scene, address, width, height, &p1, &p2);
        xsdk_present_end();
    }

    xsdk_present_close();
    destroy_scene(&scene);
    status = xsdk_gpu_close();
    if (!NT_SUCCESS(status))
        xsdk_log_write("house: GPU close failed 0x%08X", (unsigned)status);
    xsdk_log_write("house: stopped");
    return 0;
}
