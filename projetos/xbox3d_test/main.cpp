#include <cstdint>
#include <cstring>

#include "xbox3d_test_shaders.h"

#include "xsdk/gpu.h"
#include "xsdk/kernel.h"
#include "xsdk/log.h"
#include "xsdk/present.h"
#include "xsdk/shader.h"
#include "xsdk/splash.h"

namespace {

constexpr uint32_t kBuffers = 2;
constexpr uint32_t kSwapInterval = 1;
constexpr uint32_t kSplashMs = 1800;
constexpr uint32_t kBeginTimeoutMs = 5000;
constexpr uint32_t kClearColor = 0xFF101A30;

// A small, centered square. Position is clip-space XY; each vertex also has RGBA.
constexpr uint32_t kVertexCount = 6;
constexpr uint32_t kFloatsPerVertex = 6;
constexpr uint32_t kVertexStride = kFloatsPerVertex * sizeof(float);
constexpr uint32_t kVertexBytes = kVertexCount * kVertexStride;

const XsdkVertexElement kVertexLayout[] = {
    {
        .usage = XSDK_USAGE_POSITION,
        .format = XSDK_VERTEX_FLOAT2,
        .offset_bytes = 0,
    },
    {
        .usage = XSDK_USAGE_COLOR,
        .format = XSDK_VERTEX_FLOAT4,
        .offset_bytes = 2 * sizeof(float),
    },
};

const float kVertices[kVertexCount][kFloatsPerVertex] = {
    {-0.22f, -0.22f, 1.0f, 0.25f, 0.20f, 1.0f},
    { 0.22f, -0.22f, 0.20f, 1.0f, 0.35f, 1.0f},
    {-0.22f,  0.22f, 0.25f, 0.45f, 1.0f, 1.0f},
    {-0.22f,  0.22f, 0.25f, 0.45f, 1.0f, 1.0f},
    { 0.22f, -0.22f, 0.20f, 1.0f, 0.35f, 1.0f},
    { 0.22f,  0.22f, 1.0f, 0.85f, 0.20f, 1.0f},
};

void uploadVertices(volatile uint32_t* buffer)
{
    uint32_t words[kVertexBytes / sizeof(uint32_t)] = {};
    std::memcpy(words, kVertices, sizeof(kVertices));
    for (uint32_t i = 0; i < kVertexBytes / sizeof(uint32_t); ++i)
        buffer[i] = words[i];
    xsdk_gpu_invalidate(xsdk_gpu_address(buffer), kVertexBytes);
}

} // namespace

int main()
{
    xsdk_log_write("xbox3d_test: showing XSDK splash");
    const NTSTATUS splashStatus = xsdk_splash_show(kSplashMs);
    if (!NT_SUCCESS(splashStatus))
        xsdk_log_write("xbox3d_test: splash failed 0x%08X", (unsigned)splashStatus);

    NTSTATUS status = xsdk_gpu_open();
    if (!NT_SUCCESS(status)) {
        xsdk_log_write("xbox3d_test: GPU open failed 0x%08X", (unsigned)status);
        return 1;
    }

    XsdkShader vertexShader = {};
    XsdkShader pixelShader = {};
    bool vertexLoaded = false;
    bool pixelLoaded = false;
    bool presentOpen = false;
    volatile uint32_t* vertexBuffer = nullptr;

    status = xsdk_shader_load(
        &vertexShader, square3d_vert.container, square3d_vert.container_bytes);
    if (!NT_SUCCESS(status)) {
        xsdk_log_write("xbox3d_test: vertex shader load failed 0x%08X", (unsigned)status);
        goto cleanup;
    }
    vertexLoaded = true;

    status = xsdk_shader_load(
        &pixelShader, square3d_frag.container, square3d_frag.container_bytes);
    if (!NT_SUCCESS(status)) {
        xsdk_log_write("xbox3d_test: pixel shader load failed 0x%08X", (unsigned)status);
        goto cleanup;
    }
    pixelLoaded = true;

    {
        const uint32_t strides[1] = {kVertexStride};
        status = xsdk_shader_set_vertex_layout(
            &vertexShader, kVertexLayout,
            sizeof(kVertexLayout) / sizeof(kVertexLayout[0]), strides);
        if (!NT_SUCCESS(status)) {
            xsdk_log_write("xbox3d_test: vertex layout failed 0x%08X", (unsigned)status);
            goto cleanup;
        }
    }

    vertexBuffer = xsdk_gpu_alloc(kVertexBytes);
    if (!vertexBuffer) {
        xsdk_log_write("xbox3d_test: vertex buffer allocation failed");
        goto cleanup;
    }
    uploadVertices(vertexBuffer);

    {
        uint32_t width = 0;
        uint32_t height = 0;
        status = xsdk_present_open(
            XSDK_DISPLAY_720P, kBuffers, kSwapInterval, &width, &height);
        if (!NT_SUCCESS(status)) {
            xsdk_log_write("xbox3d_test: present open failed 0x%08X", (unsigned)status);
            goto cleanup;
        }
        presentOpen = true;
        xsdk_log_write("xbox3d_test: display opened at %ux%u", (unsigned)width, (unsigned)height);

        XsdkRaster raster = {};
        raster.cull = XSDK_CULL_NONE;
        XsdkRasterState rasterState = {};
        xsdk_gpu_raster_state(&rasterState, &raster);

        XsdkDepthStencil depth = {};
        depth.depth_test = false;
        XsdkDepthStencilState depthState = {};
        xsdk_gpu_depth_stencil_state(&depthState, &depth);

        bool running = true;
        while (running) {
            INPUT_STATE input = {};
            if (XamInputGetState(0, 0, &input) == ERROR_SUCCESS &&
                (input.gamepad.buttons & INPUT_GAMEPAD_BACK))
                running = false;

            uint32_t frameAddress = 0;
            status = xsdk_present_begin(&frameAddress, kBeginTimeoutMs);
            if (!NT_SUCCESS(status)) {
                xsdk_log_write("xbox3d_test: present begin failed 0x%08X", (unsigned)status);
                break;
            }

            xsdk_gpu_set_target(width, height);
            xsdk_gpu_set_shaders(&vertexShader, &pixelShader);
            xsdk_built_shader_set_literals(&square3d_vert);
            xsdk_built_shader_set_literals(&square3d_frag);
            xsdk_gpu_set_raster(&rasterState);
            xsdk_gpu_set_depth_stencil(&depthState);
            xsdk_gpu_set_vertices(0, xsdk_gpu_address(vertexBuffer), kVertexBytes);
            xsdk_gpu_draw(XSDK_PRIMITIVE_TRIANGLE_LIST, kVertexCount);
            xsdk_gpu_resolve(frameAddress, width, height, kClearColor);
            xsdk_present_end();
        }
    }

cleanup:
    if (presentOpen)
        xsdk_present_close();
    if (vertexBuffer) {
        (void)xsdk_gpu_wait(xsdk_gpu_fence(), 1000);
        xsdk_gpu_free(vertexBuffer);
    }
    if (pixelLoaded)
        xsdk_shader_free(&pixelShader);
    if (vertexLoaded)
        xsdk_shader_free(&vertexShader);

    status = xsdk_gpu_close();
    if (!NT_SUCCESS(status))
        xsdk_log_write("xbox3d_test: GPU close failed 0x%08X", (unsigned)status);
    xsdk_log_write("xbox3d_test: stopped");
    return 0;
}
