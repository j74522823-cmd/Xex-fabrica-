// Backend do Xbox 360 (xsdk) para o Bad Ice-Cream: vídeo (sprites), controles, áudio e main().
// NÃO foi compilado com a toolchain PowerPC nem rodado no console (só checagem de sintaxe no PC com os headers do xsdk).
// Dados: copie a pasta gerada por tools/export_runtime.py para <pasta do .xex>/data/ (atlas.txt, atlas*.argb, levels/, snd/, snd.txt).
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include <map>
#include <string>
#include <vector>

#include "platform.hpp"
#include "badicecream_shaders.h"
#include "xsdk/audio.h"
#include "xsdk/display.h"
#include "xsdk/gpu.h"
#include "xsdk/kernel.h"
#include "xsdk/log.h"
#include "xsdk/present.h"
#include "xsdk/shader.h"
#include "xsdk/text.h"
#include "xsdk/texture.h"
#include "xsdk/thread.h"

namespace bic {
namespace {

enum {
    MAX_PAGES = 8,
    BUFFERS = 2,
    SWAP_INTERVAL = 1,
    BEGIN_TIMEOUT_MS = 5000,
    FENCE_TIMEOUT_MS = 1000,
    // Vértice: x, y, u, v, r, g, b, a (8 floats). Quad = 4 vértices.
    VERTEX_FLOATS = 8,
    STRIDE_BYTES = VERTEX_FLOATS * 4,
    QUAD_VERTEX_BYTES = 4 * STRIDE_BYTES,
    QUADS_PER_DRAW = 1024,          // 4096 vértices: cabe nos índices de 16 bits
    DRAWS_PER_SLOT = 4,
    QUADS_PER_SLOT = QUADS_PER_DRAW * DRAWS_PER_SLOT,
    SLOT_BYTES = QUADS_PER_SLOT * QUAD_VERTEX_BYTES,
    SLOTS = 3,
    INDICES_PER_QUAD = 6,
    MAX_VOICES = 24,
    FEEDER_STACK_BYTES = 64 * 1024,
    MUSIC_VOICE = 0,
};

const uint32_t kQuadIndices[INDICES_PER_QUAD] = {0, 1, 2, 2, 1, 3};
const XsdkVertexElement kLayout[] = {
    {.usage = XSDK_USAGE_POSITION, .format = XSDK_VERTEX_FLOAT2, .offset_bytes = 0},    // location 0
    {.usage = XSDK_USAGE_COLOR, .format = XSDK_VERTEX_FLOAT4, .offset_bytes = 16},      // location 1
    {.usage = XSDK_USAGE_TEXCOORD, .format = XSDK_VERTEX_FLOAT2, .offset_bytes = 8},    // location 2
};

struct Sound { std::vector<int16_t> pcm; bool loop = false; };
struct Voice { const Sound* snd = nullptr; size_t pos = 0; bool active = false; float gain = 1.0f; };

class XboxPlatform : public Platform {
public:
    std::string dataDir() const override { return "game:/data/"; }

    bool init() override {
        NTSTATUS st = xsdk_gpu_open();
        if (!NT_SUCCESS(st)) { xsdk_log_write("bic: xsdk_gpu_open falhou 0x%08X", (unsigned)st); return false; }
        gpuOpen = true;
        st = xsdk_shader_load(&vs, sprite_vert.container, sprite_vert.container_bytes);
        if (NT_SUCCESS(st)) st = xsdk_shader_load(&ps, sprite_frag.container, sprite_frag.container_bytes);
        if (NT_SUCCESS(st)) {
            const uint32_t strides[1] = {STRIDE_BYTES};
            st = xsdk_shader_set_vertex_layout(&vs, kLayout, sizeof kLayout / sizeof kLayout[0], strides);
        }
        if (!NT_SUCCESS(st)) { xsdk_log_write("bic: shaders falharam 0x%08X", (unsigned)st); return false; }
        shadersOk = true;
        // Vértices (SLOTS blocos) e depois a lista de índices repetida.
        const uint32_t indexBytes = xsdk_gpu_repeated_index_bytes(kQuadIndices, INDICES_PER_QUAD, QUADS_PER_DRAW);
        ring = xsdk_gpu_alloc(SLOTS * SLOT_BYTES + indexBytes);
        if (!ring) { xsdk_log_write("bic: xsdk_gpu_alloc falhou"); return false; }
        ringAddress = xsdk_gpu_address(ring);
        xsdk_gpu_repeat_indices(&indices, ring + (SLOTS * SLOT_BYTES) / 4, kQuadIndices, INDICES_PER_QUAD, QUADS_PER_DRAW);
        xsdk_gpu_invalidate(indices.address, indexBytes);

        XsdkSampler sampler = {};
        sampler.mag_filter = sampler.min_filter = sampler.mip_filter = XSDK_FILTER_POINT;
        sampler.address_u = sampler.address_v = sampler.address_w = XSDK_ADDRESS_CLAMP;
        xsdk_texture_sampler_state(&samplerState, &sampler);

        XsdkBlend blend = {};
        blend.color_source = XSDK_BLEND_SRC_ALPHA; blend.color_dest = XSDK_BLEND_ONE_MINUS_SRC_ALPHA; blend.color_op = XSDK_BLEND_OP_ADD;
        blend.alpha_source = XSDK_BLEND_ONE; blend.alpha_dest = XSDK_BLEND_ONE_MINUS_SRC_ALPHA; blend.alpha_op = XSDK_BLEND_OP_ADD;
        blend.write_mask = XSDK_WRITE_ALL;
        xsdk_gpu_blend_state(&blendState, &blend);
        XsdkDepthStencil ds = {}; ds.depth_test = false;
        xsdk_gpu_depth_stencil_state(&depthState, &ds);
        XsdkRaster ras = {}; ras.cull = XSDK_CULL_NONE;
        xsdk_gpu_raster_state(&rasterState, &ras);

        st = xsdk_text_open();
        if (!NT_SUCCESS(st)) { xsdk_log_write("bic: xsdk_text_open falhou 0x%08X", (unsigned)st); return false; }
        textOpen = true;
        st = xsdk_present_open(XSDK_DISPLAY_720P, BUFFERS, SWAP_INTERVAL, &width, &height);
        if (!NT_SUCCESS(st)) { xsdk_log_write("bic: xsdk_present_open falhou 0x%08X", (unsigned)st); return false; }
        presentOpen = true;
        // Palco 550x550 centralizado, escalado pela altura.
        scale = (float)height / (float)SCREEN;
        offX = ((float)width - (float)SCREEN * scale) * 0.5f;
        offY = 0.0f;

        pthread_mutex_init(&audioLock, nullptr); lockOk = true;
        if (NT_SUCCESS(xsdk_audio_open(0))) {
            audioOpen = true;
            if (!NT_SUCCESS(xsdk_thread_create(&feeder, FEEDER_STACK_BYTES, &XboxPlatform::feedEntry, this)))
                xsdk_log_write("bic: thread de áudio falhou");
        } else xsdk_log_write("bic: xsdk_audio_open falhou (segue sem som)");
        return true;
    }

    // Os dois primeiros controles conectados (índices 0 a 3) viram jogador 1 e 2.
    bool pump(PadState pads[2]) override {
        int found = 0;
        pads[0] = PadState(); pads[1] = PadState();
        for (uint32_t i = 0; i < 4 && found < 2; i++) {
            INPUT_STATE in = {};
            if (XamInputGetState(i, 0, &in) != ERROR_SUCCESS) continue;
            const INPUT_GAMEPAD& g = in.gamepad;
            PadState& p = pads[found++];
            p.connected = true;
            const int dead = 14000;
            p.left = (g.buttons & INPUT_GAMEPAD_DPAD_LEFT) || g.thumb_lx < -dead;
            p.right = (g.buttons & INPUT_GAMEPAD_DPAD_RIGHT) || g.thumb_lx > dead;
            p.up = (g.buttons & INPUT_GAMEPAD_DPAD_UP) || g.thumb_ly > dead;
            p.down = (g.buttons & INPUT_GAMEPAD_DPAD_DOWN) || g.thumb_ly < -dead;
            p.shoot = (g.buttons & (INPUT_GAMEPAD_A | INPUT_GAMEPAD_B | INPUT_GAMEPAD_X | INPUT_GAMEPAD_Y |
                                    INPUT_GAMEPAD_LEFT_SHOULDER | INPUT_GAMEPAD_RIGHT_SHOULDER)) != 0;
            p.start = (g.buttons & INPUT_GAMEPAD_START) != 0;
            p.back = (g.buttons & INPUT_GAMEPAD_BACK) != 0;
            // Um direcional por vez (o jogo anda em 4 direções): o eixo dominante vence no analógico.
            if (g.thumb_lx != 0 || g.thumb_ly != 0) {
                int ax = g.thumb_lx < 0 ? -g.thumb_lx : g.thumb_lx, ay = g.thumb_ly < 0 ? -g.thumb_ly : g.thumb_ly;
                if (!(g.buttons & 0x000F)) { if (ax >= ay) p.up = p.down = false; else p.left = p.right = false; }
            }
        }
        return true;
    }

    void uploadPage(int page, int w, int h, const uint32_t* argb) override {
        if (page < 0 || page >= MAX_PAGES) return;
        XsdkTexture& t = pages[page];
        NTSTATUS st = xsdk_texture_create(&t, XSDK_FORMAT_A8R8G8B8, (uint32_t)w, (uint32_t)h, 1, true);
        if (!NT_SUCCESS(st)) { xsdk_log_write("bic: textura %d falhou 0x%08X", page, (unsigned)st); return; }
        xsdk_texture_upload(&t, 0, argb, (uint32_t)w * 4);
        xsdk_gpu_invalidate(t.address, t.size_bytes);
        pageOk[page] = true;
    }

    void present(const DrawList& list) override {
        uint32_t address;
        NTSTATUS st = xsdk_present_begin(&address, BEGIN_TIMEOUT_MS);
        if (!NT_SUCCESS(st)) { xsdk_log_write("bic: xsdk_present_begin falhou 0x%08X", (unsigned)st); return; }
        slot = (slot + 1) % SLOTS;
        // O slot só é reescrito quando a GPU passou do quadro que o usou.
        if (slotFence[slot]) {
            st = xsdk_gpu_wait(slotFence[slot], FENCE_TIMEOUT_MS);
            if (!NT_SUCCESS(st)) xsdk_log_write("bic: espera do slot falhou 0x%08X", (unsigned)st);
        }
        xsdk_gpu_set_target(width, height);
        drawQuads(list);
        for (size_t i = 0; i < list.texts.size(); i++) {
            const TextItem& t = list.texts[i];
            int sc = (int)(t.scale * scale + 0.5f); if (sc < 1) sc = 1; if (sc > 8) sc = 8;
            xsdk_text_draw((int32_t)(offX + t.x * scale), (int32_t)(offY + t.y * scale), (uint32_t)sc, t.argb, t.s.c_str());
        }
        xsdk_gpu_resolve(address, width, height, list.clearArgb);
        slotFence[slot] = xsdk_gpu_fence();
        xsdk_present_end();
    }

    void loadSound(const std::string& name, const int16_t* pcm, size_t frames, bool loop) override {
        Sound& s = sounds[name]; s.pcm.assign(pcm, pcm + frames); s.loop = loop;
    }
    void playSound(const std::string& name) override {
        std::map<std::string, Sound>::iterator it = sounds.find(name);
        if (it == sounds.end() || !lockOk) return;
        pthread_mutex_lock(&audioLock);
        for (int i = 1; i < MAX_VOICES; i++)
            if (!voices[i].active) { voices[i].snd = &it->second; voices[i].pos = 0; voices[i].gain = 0.8f; voices[i].active = true; break; }
        pthread_mutex_unlock(&audioLock);
    }
    void playMusic(const std::string& name) override {
        if (!lockOk) return;
        pthread_mutex_lock(&audioLock);
        voices[MUSIC_VOICE].active = false;
        std::map<std::string, Sound>::iterator it = sounds.find(name);
        if (!name.empty() && it != sounds.end()) {
            voices[MUSIC_VOICE].snd = &it->second; voices[MUSIC_VOICE].pos = 0; voices[MUSIC_VOICE].gain = 0.5f; voices[MUSIC_VOICE].active = true;
        }
        pthread_mutex_unlock(&audioLock);
    }
    double now() override {
        struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
        return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
    }
    void shutdown() override {
        if (audioOpen) {
            xsdk_audio_close();
            if (feeder) { static const int64_t timeout = -50000000; NtWaitForSingleObjectEx(feeder, USER_MODE, 0, &timeout); NtClose(feeder); feeder = 0; }
            audioOpen = false;
        }
        if (presentOpen) { xsdk_present_close(); presentOpen = false; }
        if (textOpen) { xsdk_text_close(); textOpen = false; }
        if (gpuOpen) {
            xsdk_gpu_wait(xsdk_gpu_fence(), FENCE_TIMEOUT_MS);
            for (int i = 0; i < MAX_PAGES; i++) if (pageOk[i]) { xsdk_texture_free(&pages[i]); pageOk[i] = false; }
            if (ring) { xsdk_gpu_free(ring); ring = nullptr; }
            if (shadersOk) { xsdk_shader_free(&ps); xsdk_shader_free(&vs); shadersOk = false; }
            xsdk_gpu_close(); gpuOpen = false;
        }
    }

private:
    // ---------------- vídeo
    uint32_t width = 0, height = 0; float scale = 1, offX = 0, offY = 0;
    bool gpuOpen = false, textOpen = false, presentOpen = false, shadersOk = false;
    XsdkShader vs = {}, ps = {};
    volatile uint32_t* ring = nullptr; uint32_t ringAddress = 0; XsdkRepeatedIndices indices = {};
    XsdkSamplerState samplerState = {}; XsdkBlendState blendState = {}; XsdkDepthStencilState depthState = {}; XsdkRasterState rasterState = {};
    XsdkTexture pages[MAX_PAGES] = {}; bool pageOk[MAX_PAGES] = {};
    uint32_t slot = 0, slotFence[SLOTS] = {};

    static void put(volatile uint32_t* dst, const float* src, int n) {
        for (int i = 0; i < n; i++) { uint32_t w; memcpy(&w, &src[i], 4); dst[i] = w; }   // memória da GPU: stores de 32 bits
    }

    void drawQuads(const DrawList& list) {
        float to_clip[4] = {2.0f / (float)width, -2.0f / (float)height, -1.0f, 1.0f};
        xsdk_gpu_set_shaders(&vs, &ps);
        xsdk_built_shader_set_literals(&sprite_vert);
        xsdk_built_shader_set_literals(&sprite_frag);
        xsdk_gpu_set_vertex_constants(SPRITE_VERT_PUSH, to_clip, SPRITE_VERT_PUSH_REGISTERS);
        xsdk_gpu_set_blend(&blendState);
        xsdk_gpu_set_depth_stencil(&depthState);
        xsdk_gpu_set_raster(&rasterState);

        const uint32_t slotBase = slot * SLOT_BYTES;
        uint32_t written = 0;   // quads escritos no slot
        size_t i = 0;
        while (i < list.quads.size()) {
            const int page = list.quads[i].page;
            // Lote: quads consecutivos da mesma página (a ordem de desenho é a do z-order do render.cpp).
            uint32_t batchStart = written;
            while (i < list.quads.size() && list.quads[i].page == page && written < QUADS_PER_SLOT) {
                const Quad& q = list.quads[i++];
                const float x0 = offX + q.x0 * scale, y0 = offY + q.y0 * scale, x1 = offX + q.x1 * scale, y1 = offY + q.y1 * scale;
                const float v[4][VERTEX_FLOATS] = {
                    {x0, y0, q.u0, q.v0, q.r, q.g, q.b, q.a}, {x1, y0, q.u1, q.v0, q.r, q.g, q.b, q.a},
                    {x0, y1, q.u0, q.v1, q.r, q.g, q.b, q.a}, {x1, y1, q.u1, q.v1, q.r, q.g, q.b, q.a}};
                put(ring + (slotBase + written * QUAD_VERTEX_BYTES) / 4, &v[0][0], 4 * VERTEX_FLOATS);
                written++;
            }
            if (page >= 0 && page < MAX_PAGES && pageOk[page] && written > batchStart) {
                xsdk_gpu_set_texture(SPRITE_FRAG_SAMPLER_0_0, &pages[page], &samplerState);
                // Desenha em pedaços de até QUADS_PER_DRAW.
                for (uint32_t first = batchStart; first < written;) {
                    const uint32_t n = (written - first) < (uint32_t)QUADS_PER_DRAW ? (written - first) : (uint32_t)QUADS_PER_DRAW;
                    const uint32_t address = ringAddress + slotBase + first * QUAD_VERTEX_BYTES;
                    xsdk_gpu_invalidate(address, n * QUAD_VERTEX_BYTES);
                    xsdk_gpu_set_vertices(0, address, n * QUAD_VERTEX_BYTES);
                    xsdk_gpu_draw_indexed(XSDK_PRIMITIVE_TRIANGLE_LIST, indices.address, n * INDICES_PER_QUAD, false);
                    first += n;
                }
            }
            if (written >= QUADS_PER_SLOT && i < list.quads.size()) { xsdk_log_write("bic: quadros demais (%u), cortando", (unsigned)list.quads.size()); break; }
        }
    }

    // ---------------- áudio: mono 48 kHz nas duas frentes
    pthread_mutex_t audioLock; bool lockOk = false, audioOpen = false;
    HANDLE feeder = 0;
    std::map<std::string, Sound> sounds;
    Voice voices[MAX_VOICES];

    static uint32_t feedEntry(void* self) { return static_cast<XboxPlatform*>(self)->feed(); }

    uint32_t feed() {
        for (;;) {
            float* frame;
            const NTSTATUS st = xsdk_audio_next_frame(100, &frame);
            if (st == STATUS_IO_TIMEOUT) continue;
            if (st != STATUS_SUCCESS) return 0;
            float mix[XSDK_AUDIO_FRAME_SAMPLES];
            for (int s = 0; s < XSDK_AUDIO_FRAME_SAMPLES; s++) mix[s] = 0.0f;
            pthread_mutex_lock(&audioLock);
            for (int v = 0; v < MAX_VOICES; v++) {
                Voice& vo = voices[v];
                if (!vo.active) continue;
                const std::vector<int16_t>& d = vo.snd->pcm;
                for (int s = 0; s < XSDK_AUDIO_FRAME_SAMPLES; s++) {
                    if (vo.pos >= d.size()) { if (vo.snd->loop && !d.empty()) vo.pos = 0; else { vo.active = false; break; } }
                    mix[s] += (float)d[vo.pos++] * (1.0f / 32768.0f) * vo.gain;
                }
            }
            pthread_mutex_unlock(&audioLock);
            volatile float* out = frame;
            for (int c = 0; c < XSDK_AUDIO_CHANNELS; c++)
                for (int s = 0; s < XSDK_AUDIO_FRAME_SAMPLES; s++) {
                    float x = mix[s]; if (x > 1.0f) x = 1.0f; if (x < -1.0f) x = -1.0f;
                    const bool front = c == XSDK_AUDIO_FRONT_LEFT || c == XSDK_AUDIO_FRONT_RIGHT;
                    out[c * XSDK_AUDIO_FRAME_SAMPLES + s] = front ? x : 0.0f;
                }
            xsdk_audio_queue_frame();
        }
    }
};

}  // namespace
}  // namespace bic

int main(void) {
    bic::XboxPlatform pf;
    bic::Options opt;   // título escolhe 1 jogador ou coop; coop = START no 2º controle
    xsdk_log_write("badicecream: iniciando");
    const int r = bic::runGame(pf, opt);
    xsdk_log_write("badicecream: fim (%d)", r);
    return r;
}
