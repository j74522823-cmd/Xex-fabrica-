/* main_xsdk.c - ponto de entrada no Xbox 360: inicializa, le os controles, roda o loop. */
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "xsdk/gpu.h"
#include "xsdk/xam.h"       /* XamInputGetState, XINPUT_STATE */

#include "draw_scene.h"
#include "render.h"

#define MAP_PATH "game:/farm.rfm"

static float stick(short v) {
    const float dead = 7849.0f;              /* zona morta padrao do XInput (esquerdo) */
    float f = (float)v;
    if (f > dead) return (f - dead) / (32767.0f - dead);
    if (f < -dead) return (f + dead) / (32768.0f - dead);
    return 0.0f;
}

static void read_pads(Pad pads[MAX_PLAYERS]) {
    for (int i = 0; i < MAX_PLAYERS; i++) {
        XINPUT_STATE st;                     /* XSDK: confirme o nome no xam.h */
        uint16_t prev = pads[i].buttons;
        memset(&pads[i], 0, sizeof pads[i]);
        if (XamInputGetState(i, 0, &st) != 0) continue;   /* 0 = ERROR_SUCCESS */
        Pad *p = &pads[i];
        p->connected = 1;
        p->buttons = st.Gamepad.wButtons;
        p->pressed = p->buttons & ~prev;
        p->lx = stick(st.Gamepad.sThumbLX);
        p->ly = stick(st.Gamepad.sThumbLY);
        p->rx = stick(st.Gamepad.sThumbRX);
        p->ry = stick(st.Gamepad.sThumbRY);
        p->lt = st.Gamepad.bLeftTrigger / 255.0f;
        p->rt = st.Gamepad.bRightTrigger / 255.0f;
    }
}

static double now_s(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (double)t.tv_sec + (double)t.tv_nsec * 1e-9;
}

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    uint32_t w = 1280, h = 720;

    xsdk_gpu_open();
    /* XSDK: modo 720p, 2 buffers, sincronizado no vblank (intervalo 1) */
    xsdk_present_open(XSDK_PRESENT_720P, 2, 1, &w, &h);
    xsdk_text_open();

    static Map map;
    if (!map_load(&map, MAP_PATH)) {
        printf("nao abriu %s - copie farm.rfm para a mesma pasta do .xex\n", MAP_PATH);
        /* mostra o erro na tela por alguns segundos */
        for (int f = 0; f < 300; f++) {
            uint32_t fb;
            xsdk_present_begin(&fb, 100);
            xsdk_gpu_set_target(w, h);
            xsdk_text_draw(100, 100, 2, 0xFFFF4040, "farm.rfm nao encontrado ao lado do .xex");
            xsdk_gpu_resolve(fb, w, h, 0xFF000000);
            xsdk_present_end();
        }
        return 1;
    }
    printf("mapa: %u vertices, %u triangulos, %u lotes\n", map.num_vertices, map.num_indices / 3, map.num_batches);

    static Collision col;
    collision_build(&col, &map, 2.0f);
    static Game game;
    game_init(&game, &col, (int)w, (int)h);
    if (!render_init(&map, (int)w, (int)h)) {
        printf("falha ao carregar os shaders\n");
        return 1;
    }

    static Pad pads[MAX_PLAYERS];
    double last = now_s();
    for (;;) {
        read_pads(pads);
        /* BACK + START no controle 1 fecha o jogo (BACK sozinho e usado pelo jogador 2) */
        if ((pads[0].buttons & (PAD_BACK | PAD_START)) == (PAD_BACK | PAD_START)) break;

        double t = now_s();
        float dt = (float)(t - last);
        last = t;

        game_update(&game, pads, dt);
        game_build_cameras(&game);
        draw_scene(&game);
    }

    render_shutdown();
    collision_free(&col);
    map_free(&map);
    xsdk_text_close();
    xsdk_present_close();
    xsdk_gpu_close();
    return 0;
}
