/* Entrada do jogo no Xbox 360. */
#include <stdint.h>
#include <string.h>
#include <time.h>

#include "xsdk/kernel.h"
#include "xsdk/gpu.h"
#include "xsdk/present.h"

#include "draw_scene.h"
#include "render.h"

#define MAP_PATH "game:/farm.rfm"

static float stick(int16_t value) {
    const float dead=7849.0f, v=(float)value;
    if (v>dead) return (v-dead)/(32767.0f-dead);
    if (v< -dead) return (v+dead)/(32768.0f-dead);
    return 0.0f;
}

static void read_pads(Pad pads[MAX_PLAYERS]) {
    for (uint32_t i=0;i<MAX_PLAYERS;++i) {
        INPUT_STATE state={0};
        uint16_t previous=pads[i].buttons;
        memset(&pads[i],0,sizeof pads[i]);
        if (XamInputGetState(i,0,&state)!=ERROR_SUCCESS) continue;
        Pad *pad=&pads[i];
        pad->connected=1;
        pad->buttons=state.gamepad.buttons;
        pad->pressed=pad->buttons & (uint16_t)~previous;
        pad->lx=stick(state.gamepad.thumb_lx);
        pad->ly=stick(state.gamepad.thumb_ly);
        pad->rx=stick(state.gamepad.thumb_rx);
        pad->ry=stick(state.gamepad.thumb_ry);
        pad->lt=state.gamepad.left_trigger/255.0f;
        pad->rt=state.gamepad.right_trigger/255.0f;
    }
}

static double now_s(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC,&t);
    return (double)t.tv_sec+(double)t.tv_nsec*1e-9;
}

int main(void) {
    uint32_t width=1280,height=720;
    NTSTATUS status=xsdk_gpu_open();
    if (!NT_SUCCESS(status)) return 1;
    status=xsdk_present_open(XSDK_DISPLAY_720P,2,1,&width,&height);
    if (!NT_SUCCESS(status)) { xsdk_gpu_close(); return 1; }

    static Map map;
    if (!map_load(&map,MAP_PATH)) {
        xsdk_present_close(); xsdk_gpu_close(); return 1;
    }
    static Collision collision;
    collision_build(&collision,&map,2.0f);
    static Game game;
    game_init(&game,&collision,(int)width,(int)height);
    if (!render_init(&map,(int)width,(int)height)) {
        map_free(&map); collision_free(&collision);
        xsdk_present_close(); xsdk_gpu_close(); return 1;
    }

    static Pad pads[MAX_PLAYERS];
    double previous=now_s();
    for (;;) {
        read_pads(pads);
        if ((pads[0].buttons&(PAD_BACK|PAD_START))==(PAD_BACK|PAD_START)) break;
        double current=now_s();
        float dt=(float)(current-previous); previous=current;
        if (dt>0.1f) dt=0.1f;
        game_update(&game,pads,dt);
        game_build_cameras(&game);
        render_frame_begin();
        draw_scene(&game);
        render_frame_end();
    }

    render_shutdown();
    collision_free(&collision);
    map_free(&map);
    xsdk_present_close();
    xsdk_gpu_close();
    return 0;
}
