/* draw_scene.c - desenha o quadro (mapa, bonecos, impactos, mira, HUD) usando render.h. */
#include "draw_scene.h"
#include "render.h"

#include <stdio.h>

/* Boneco original feito de caixas: pernas, tronco, cabeca e arma quando mira. */
static void draw_player(const Player *p) {
    float bob = sinf(p->walk_cycle * 3.0f) * 0.25f;
    vec3 c = p->color;
    vec3 dark = v3_scale(c, 0.55f);
    vec3 skin = v3(0.80f, 0.66f, 0.55f);
    struct { vec3 pos, size, color; float swing; } parts[] = {
        {v3(-0.11f, 0.42f, 0), v3(0.15f, 0.84f, 0.17f), dark, bob},   /* perna esq */
        {v3( 0.11f, 0.42f, 0), v3(0.15f, 0.84f, 0.17f), dark, -bob},  /* perna dir */
        {v3(0, 1.17f, 0),      v3(0.46f, 0.66f, 0.26f), c, 0},         /* tronco */
        {v3(0, 1.62f, 0),      v3(0.22f, 0.24f, 0.24f), skin, 0},      /* cabeca */
    };
    for (unsigned i = 0; i < sizeof parts / sizeof parts[0]; i++) {
        /* posicao local -> mundo (gira com o yaw do jogador) */
        float s = sinf(p->yaw), co = cosf(p->yaw);
        vec3 lp = parts[i].pos;
        lp.z += parts[i].swing * 0.3f;
        /* eixo x local = -right = (cos, 0, -sin); eixo z local = frente = (sin, 0, cos) */
        vec3 wp = v3(p->pos.x + lp.x * co + lp.z * s, p->pos.y + lp.y, p->pos.z - lp.x * s + lp.z * co);
        mat4 m = m4_trs_y(wp, p->yaw, parts[i].size);
        render_box(&m, parts[i].color);
    }
    if (p->aim_blend > 0.1f) {
        /* bracos/arma esticados para frente, inclinados com a mira */
        float s = sinf(p->yaw), co = cosf(p->yaw);
        float reach = 0.25f + 0.2f * p->aim_blend;
        vec3 wp = v3(p->pos.x + s * reach - co * -0.12f, p->pos.y + 1.38f + sinf(p->aim_pitch) * 0.2f,
                     p->pos.z + co * reach + s * -0.12f);
        mat4 m = m4_trs_y(wp, p->yaw, v3(0.08f, 0.1f, 0.45f));
        render_box(&m, v3(0.15f, 0.15f, 0.15f));
        if (p->muzzle_flash > 0) {
            vec3 fp = v3_add(wp, v3(s * 0.3f, 0, co * 0.3f));
            mat4 f = m4_trs_y(fp, p->yaw, v3(0.12f, 0.12f, 0.12f));
            render_box(&f, v3(4.0f, 3.2f, 1.2f));
        }
    }
}

void draw_scene(const Game *g) {
    render_frame_begin();
    for (int v = 0; v < g->num_views; v++) {
        const Camera *cam = &g->cams[v];
        render_view_begin(cam->vp_x, cam->vp_y, cam->vp_w, cam->vp_h, &cam->view_proj, cam->eye);
        render_map();
        for (int i = 0; i < MAX_PLAYERS; i++)
            if (g->players[i].active) draw_player(&g->players[i]);
        for (int i = 0; i < MAX_IMPACTS; i++) {
            const Impact *im = &g->impacts[i];
            if (im->life <= 0) continue;
            mat4 m = m4_trs_y(v3_add(im->pos, v3_scale(im->normal, 0.02f)), 0, v3(0.07f, 0.07f, 0.07f));
            render_box(&m, v3(0.08f, 0.07f, 0.06f));
        }
        /* mira no centro de cada tela quando o jogador esta mirando */
        const Player *p = &g->players[v];
        int cx = cam->vp_x + cam->vp_w / 2, cy = cam->vp_y + cam->vp_h / 2;
        if (p->aim_blend > 0.7f) render_text(cx - 4, cy - 8, 1, 0xFFFF3020, "+");
        char label[32];
        snprintf(label, sizeof label, "JOGADOR %d", v + 1);
        render_text(cam->vp_x + 24, cam->vp_y + 16, 1, 0xC0FFFFFF, label);
    }
    if (g->num_views == 1)
        render_text(g->screen_w - 360, 16, 1, 0x90FFFFFF, "Controle 2: START para entrar");
    render_frame_end();
}
