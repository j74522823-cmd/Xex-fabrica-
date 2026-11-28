/* sim.c - testa a logica do jogo no PC, sem video: anda, corre, gira, mira e atira. */
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "../src/game.h"

static double now_s(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}

int main(int argc, char **argv) {
    const char *path = argc > 1 ? argv[1] : "build/farm.rfm";
    Map map;
    if (!map_load(&map, path)) {
        printf("FALHOU: nao abriu %s\n", path);
        return 1;
    }
    printf("mapa: %u vertices, %u triangulos, %u lotes\n", map.num_vertices, map.num_indices / 3, map.num_batches);

    double t0 = now_s();
    Collision col;
    collision_build(&col, &map, 2.0f);
    printf("colisao: %u triangulos, grade %dx%d, %.1f ms para montar\n",
           col.num_tris, col.cells_x, col.cells_z, (now_s() - t0) * 1000);

    Game g;
    game_init(&g, &col, 1280, 720);
    printf("spawn: (%.2f, %.2f, %.2f)\n", g.spawn.x, g.spawn.y, g.spawn.z);

    Pad pads[MAX_PLAYERS];
    memset(pads, 0, sizeof pads);
    pads[0].connected = 1;
    pads[1].connected = 1;

    const float dt = 1.0f / 60.0f;
    int failures = 0, wall_hits = 0, respawns = 0;
    double update_time = 0;
    float max_step_xz = 0;
    int shots_landed = 0;

    for (int frame = 0; frame < 60 * 120; frame++) {     /* 2 minutos de jogo */
        int phase = (frame / 180) % 8;
        for (int i = 0; i < MAX_PLAYERS; i++) {
            Pad *p = &pads[i];
            uint16_t prev = p->buttons;
            memset(p, 0, sizeof *p);
            p->connected = 1;
            float turn = (i == 0) ? 0.35f : -0.5f;
            switch (phase) {
            case 0: p->ly = 1; break;                                   /* anda */
            case 1: p->ly = 1; p->buttons = PAD_A; p->lx = turn; break;  /* corre virando */
            case 2: p->ly = 1; p->buttons = PAD_A; break;               /* corre reto (vai bater em coisas) */
            case 3: p->ly = -1; if (frame % 180 == 10) p->buttons = PAD_B; break; /* recua + giro rapido */
            case 4: p->lt = 1; p->rt = (frame % 30) < 3; p->lx = 0.3f; break;     /* mira e atira */
            case 5: p->ly = 1; p->lx = -turn; break;
            case 6: p->ly = 1; p->buttons = PAD_A; p->lx = turn * 0.3f; break;
            case 7: p->rx = 1; p->ry = 0.5f; break;                     /* so olha em volta */
            }
            if (i == 1 && frame == 30) p->buttons |= PAD_START;          /* jogador 2 entra */
            p->pressed = p->buttons & ~prev;
        }

        vec3 before[MAX_PLAYERS];
        for (int i = 0; i < MAX_PLAYERS; i++) before[i] = g.players[i].pos;
        int impacts_before = 0;
        for (int k = 0; k < MAX_IMPACTS; k++) impacts_before += g.impacts[k].life > 5.99f;

        double u0 = now_s();
        game_update(&g, pads, dt);
        game_build_cameras(&g);
        update_time += now_s() - u0;

        for (int k = 0; k < MAX_IMPACTS; k++) shots_landed += g.impacts[k].life > 6.0f - dt * 1.5f && g.impacts[k].life <= 6.0f ? 1 : 0;
        (void)impacts_before;

        for (int i = 0; i < MAX_PLAYERS; i++) {
            Player *pl = &g.players[i];
            if (!pl->active) continue;
            vec3 d = v3_sub(pl->pos, before[i]);
            float step = sqrtf(d.x * d.x + d.z * d.z);
            if (step > 1.0f) respawns++;                 /* teleporte = respawn */
            else if (step > max_step_xz) max_step_xz = step;
            /* checagem 1: jogador no chao precisa ter chao embaixo */
            float gy;
            if (pl->grounded) {
                if (!collision_ground(&col, pl->pos.x, pl->pos.z, pl->pos.y + 0.05f, pl->pos.y - 0.6f, &gy, NULL)) {
                    if (failures < 5) printf("  falha: jogador %d sem chao em (%.2f %.2f %.2f)\n", i, pl->pos.x, pl->pos.y, pl->pos.z);
                    failures++;
                }
            }
            /* checagem 2: o corpo nao pode estar dentro de parede */
            vec3 s = v3(pl->pos.x, pl->pos.y + 1.0f, pl->pos.z), s0 = s;
            if (collision_push_sphere(&col, &s, 0.30f) && v3_len(v3_sub(s, s0)) > 0.02f) wall_hits++;
        }
        if (frame % 600 == 0) {
            Player *a = &g.players[0], *b = &g.players[1];
            printf("t=%3ds  J1 (%.1f, %.1f, %.1f)%s   J2 %s (%.1f, %.1f, %.1f)  telas=%d\n", frame / 60,
                   a->pos.x, a->pos.y, a->pos.z, a->grounded ? "" : " no ar",
                   b->active ? "ativo" : "fora ", b->pos.x, b->pos.y, b->pos.z, g.num_views);
        }
    }

    printf("\nresultado:\n");
    printf("  quadros sem chao embaixo: %d\n", failures);
    printf("  quadros com corpo dentro de parede (>2cm): %d\n", wall_hits);
    printf("  respawns: %d, maior passo por quadro: %.3f m\n", respawns, max_step_xz);
    printf("  tiros que acertaram o cenario: %d\n", shots_landed);
    printf("  logica por quadro (2 jogadores): %.3f ms no PC\n", update_time / (60 * 120) * 1000);

    /* camera: viewports da tela dividida */
    for (int i = 0; i < g.num_views; i++)
        printf("  camera %d: viewport %d,%d %dx%d\n", i, g.cams[i].vp_x, g.cams[i].vp_y, g.cams[i].vp_w, g.cams[i].vp_h);

    collision_free(&col);
    map_free(&map);
    int ok = failures == 0 && wall_hits < 30;
    printf("%s\n", ok ? "OK" : "PROBLEMAS");
    return ok ? 0 : 1;
}
