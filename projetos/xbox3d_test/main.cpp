#include <cmath>
#include <cstdint>
#include <cstring>

#include "square3d_shaders.h"

#include "xsdk/display.h"
#include "xsdk/gpu.h"
#include "xsdk/kernel.h"
#include "xsdk/log.h"
#include "xsdk/present.h"
#include "xsdk/shader.h"

namespace {

constexpr uint32_t kWidth = 1280;
constexpr uint32_t kHeight = 720;
constexpr uint32_t kVertexCount = 6;
constexpr uint32_t kFloatsPerVertex = 7;
constexpr uint32_t kVertexStride = kFloatsPerVertex * sizeof(float);
constexpr uint32_t kClearColor = 0xFF101A30;
constexpr int16_t kDeadZone = 6000;

const XsdkVertexElement kVertexLayout[] = {
    {
        .usage = XSDK_USAGE_POSITION,
        .format = XSDK_VERTEX_FLOAT3,
        .offset_bytes = 0,
    },
    {
        .usage = XSDK_USAGE_COLOR,
        .format = XSDK_VERTEX_FLOAT4,
        .offset_bytes = 3 * sizeof(float),
    },
};

const float kVertices[kVertexCount][kFloatsPerVertex] = {
    {-1.0f, -1.0f, 0.0f, 1.0f, 0.20f, 0.20f, 1.0f},
    { 1.0f, -1.0f, 0.0f, 0.20f, 1.0f, 0.30f, 1.0f},
    {-1.0f,  1.0f, 0.0f, 0.20f, 0.50f, 1.0f, 1.0f},
    {-1.0f,  1.0f, 0.0f, 0.20f, 0.50f, 1.0f, 1.0f},
    { 1.0f, -1.0f, 0.0f, 0.20f, 1.0f, 0.30f, 1.0f},
    { 1.0f,  1.0f, 0.0f, 1.0f, 0.85f, 0.20f, 1.0f},
};

void multiplyMatrix(float out[16], const float a[16], const float b[16])
{
    float result[16] = {};
    for (int column = 0; column < 4; ++column) {
        for (int row = 0; row < 4; ++row) {
            for (int k = 0; k < 4; ++k)
                result[column * 4 + row] += a[k * 4 + row] * b[column * 4 + k];
        }
    }
    std::memcpy(out, result, sizeof(result));
}

void makeMvp(float out[16], float angleX, float angleY, float aspect)
{
    const float sx = std::sin(angleX);
    const float cx = std::cos(angleX);
    const float sy = std::sin(angleY);
    const float cy = std::cos(angleY);

    const float rotationX[16] = {
        1, 0,  0, 0,
        0, cx, sx, 0,
        0, -sx, cx, 0,
        0, 0,  0, 1
    };
    const float rotationY[16] = {
        cy, 0, -sy, 0,
        0,  1, 0,  0,
        sy, 0, cy,  0,
        0,  0, 0,  1
    };
    const float translation[16] = {
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, -3.5f, 1
    };

    constexpr float nearPlane = 0.1f;
    constexpr float farPlane = 50.0f;
    constexpr float fov = 0.78539816339f;
    const float f = 1.0f / std::tan(fov * 0.5f);
    const float projection[16] = {
        f / aspect, 0, 0, 0,
        0, f, 0, 0,
        0, 0, farPlane / (nearPlane - farPlane), -1,
        0, 0, (farPlane * nearPlane) / (nearPlane - farPlane), 0
    };

    float rotation[16];
    float modelRotation[16];
    float model[16];
    float viewModel[16];
    multiplyMatrix(rotation, rotationY, rotationX);
    std::memcpy(modelRotation, rotation, sizeof(rotation));
    multiplyMatrix(model, translation, modelRotation);
    multiplyMatrix(viewModel, projection, model);
    std::memcpy(out, viewModel, sizeof(viewModel));
}

void uploadVertices(volatile uint32_t* buffer)
{
    for (uint32_t i = 0; i < kVertexCount; ++i) {
        for (uint32_t j = 0; j < kFloatsPerVertex; ++j) {
            uint32_t word = 0;
            std::memcpy(&word, &kVertices[i][j], sizeof(word));
            buffer[i * kFloatsPerVertex + j] = word;
        }
    }
}

} // namespace

int main()
{
    xsdk_log_write("xbox3d_test: starting");

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

    vertexBuffer = xsdk_gpu_alloc(kVertexCount * kVertexStride);
    if (!vertexBuffer) {
        xsdk_log_write("xbox3d_test: vertex buffer allocation failed");
        goto cleanup;
    }
    uploadVertices(vertexBuffer);
    xsdk_gpu_invalidate(
        xsdk_gpu_address(vertexBuffer), kVertexCount * kVertexStride);

    {
        uint32_t width = 0;
        uint32_t height = 0;
        status = xsdk_present_open(
            XSDK_DISPLAY_720P, 2, 1, &width, &height);
        if (!NT_SUCCESS(status)) {
            xsdk_log_write("xbox3d_test: present open failed 0x%08X", (unsigned)status);
            goto cleanup;
        }
        presentOpen = true;
        xsdk_log_write("xbox3d_test: display %ux%u", (unsigned)width, (unsigned)height);
    }

    {
        XsdkRaster raster = {};
        raster.cull = XSDK_CULL_NONE;
        XsdkRasterState rasterState = {};
        xsdk_gpu_raster_state(&rasterState, &raster);

        XsdkDepthStencil depth = {};
        depth.depth_test = false;
        XsdkDepthStencilState depthState = {};
        xsdk_gpu_depth_stencil_state(&depthState, &depth);

        float angleX = 0.25f;
        float angleY = 0.35f;
        bool running = true;

        while (running) {
            INPUT_STATE input = {};
            if (XamInputGetState(0, 0, &input) == ERROR_SUCCESS) {
                const INPUT_GAMEPAD& pad = input.gamepad;
                if (pad.buttons & INPUT_GAMEPAD_BACK)
                    running = false;

                if (pad.thumb_lx > kDeadZone || pad.thumb_lx < -kDeadZone)
                    angleY += (float)pad.thumb_lx / 32768.0f * 0.045f;
                if (pad.thumb_ly > kDeadZone || pad.thumb_ly < -kDeadZone)
                    angleX -= (float)pad.thumb_ly / 32768.0f * 0.045f;
            }

            uint32_t frameAddress = 0;
            status = xsdk_present_begin(&frameAddress, 5000);
            if (!NT_SUCCESS(status)) {
                xsdk_log_write("xbox3d_test: present begin failed 0x%08X", (unsigned)status);
                break;
            }

            xsdk_gpu_set_target(kWidth, kHeight);
            xsdk_gpu_set_shaders(&vertexShader, &pixelShader);
            xsdk_built_shader_set_literals(&square3d_vert);
            xsdk_built_shader_set_literals(&square3d_frag);
            xsdk_gpu_set_raster(&rasterState);
            xsdk_gpu_set_depth_stencil(&depthState);
            xsdk_gpu_set_vertices(
                0, xsdk_gpu_address(vertexBuffer), kVertexCount * kVertexStride);

            float mvp[16];
            makeMvp(mvp, angleX, angleY, (float)kWidth / (float)kHeight);
            xsdk_gpu_set_vertex_constants(
                SQUARE3D_VERT_PUSH, mvp, SQUARE3D_VERT_PUSH_REGISTERS);

            xsdk_gpu_draw(XSDK_PRIMITIVE_TRIANGLE_LIST, kVertexCount);
            xsdk_gpu_resolve(frameAddress, kWidth, kHeight, kClearColor);
            (void)xsdk_gpu_fence();
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

    (void)xsdk_gpu_close();
    xsdk_log_write("xbox3d_test: stopped");
    return 0;
}
