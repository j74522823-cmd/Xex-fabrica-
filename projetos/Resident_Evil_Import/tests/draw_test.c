#include <stdio.h>
#include <string.h>
#include "../src/draw_scene.h"
extern int stub_draws, stub_boxes, stub_views; void stub_set_map(const Map *m);
int main(int c, char **v) {
    Map map; if (!map_load(&map, c > 1 ? v[1] : "build/farm.rfm")) return 1;
    stub_set_map(&map);
    Collision col; collision_build(&col, &map, 2.0f);
    Game g; game_init(&g, &col, 1280, 720);
    Pad pads[2]; memset(pads, 0, sizeof pads); pads[0].connected = pads[1].connected = 1;
    pads[1].buttons = pads[1].pressed = PAD_START;
    game_update(&g, pads, 1/60.f); pads[1].buttons = pads[1].pressed = 0;
    pads[0].lt = 1; pads[0].rt = 1;
    for (int i = 0; i < 30; i++) { game_update(&g, pads, 1/60.f); game_build_cameras(&g); draw_scene(&g); }
    printf("telas=%d draws por quadro=%d (caixas=%d)\n", stub_views, stub_draws, stub_boxes);
    /* checa se a mira projeta no centro: ponto 10m a frente da camera */
    Camera *cam = &g.cams[0];
    vec3 d = v3_norm(v3_sub(cam->target, cam->eye)), p = v3_add(cam->eye, v3_scale(d, 10));
    float *m = cam->view_proj.m;
    float x = m[0]*p.x+m[4]*p.y+m[8]*p.z+m[12], y = m[1]*p.x+m[5]*p.y+m[9]*p.z+m[13];
    float z = m[2]*p.x+m[6]*p.y+m[10]*p.z+m[14], w = m[3]*p.x+m[7]*p.y+m[11]*p.z+m[15];
    printf("ponto mirado em NDC: x=%.3f y=%.3f z=%.3f (esperado 0, 0, entre 0 e 1)\n", x/w, y/w, z/w);
    return 0;
}
