/* game.c - jogadores, controles estilo RE4, camera por cima do ombro, tela dividida. */
#include "game.h"

#include <string.h>

/* Ajustes de jogo (metros, segundos, radianos) */
#define WALK_SPEED      2.2f
#define RUN_SPEED       4.6f
#define BACK_SPEED      1.4f
#define TURN_SPEED      2.6f
#define GRAVITY         18.0f
#define STEP_HEIGHT     0.45f
#define PLAYER_RADIUS   0.32f
#define PLAYER_HEIGHT   1.75f
#define QUICKTURN_TIME  0.35f
#define AIM_TURN_SPEED  1.6f
#define AIM_PITCH_SPEED 1.2f
#define SHOOT_INTERVAL  0.35f
#define SHOT_RANGE      80.0f

#define PI_F 3.14159265f

static vec3 forward_of(float yaw) { return v3(sinf(yaw), 0, cosf(yaw)); }
static vec3 right_of(float yaw) { return v3(-cosf(yaw), 0, sinf(yaw)); }

/* Procura um ponto de chao perto do centro do mapa, com espaco livre para ficar de pe. */
static int find_spawn(Game *g, vec3 *out) {
    Collision *c = g->col;
    vec3 center = v3_scale(v3_add(c->bounds_min, c->bounds_max), 0.5f);
    float top = c->bounds_max.y + 5.0f, bottom = c->bounds_min.y - 5.0f;
    for (float r = 0; r < 60.0f; r += 1.0f) {
        int steps = r < 0.5f ? 1 : (int)(r * 6.0f);
        for (int i = 0; i < steps; i++) {
            float a = (float)i / (float)steps * 2.0f * PI_F;
            float x = center.x + cosf(a) * r, z = center.z + sinf(a) * r;
            float y;
            vec3 n;
            /* pega o chao mais alto: em areas abertas e o terreno */
            if (!collision_ground(c, x, z, top, bottom, &y, &n) || n.y < 0.9f) continue;
            /* nada em cima da cabeca? */
            float t;
            if (collision_raycast(c, v3(x, y + 0.2f, z), v3(0, 1, 0), 3.0f, &t, NULL)) continue;
            /* espaco ao redor */
            vec3 p = v3(x, y + 0.9f, z), q = p;
            if (collision_push_sphere(c, &q, 0.8f)) continue;
            *out = v3(x, y, z);
            return 1;
        }
    }
    return 0;
}

static void spawn_player(Game *g, int i) {
    Player *p = &g->players[i];
    vec3 color = p->color;
    int active = p->active;
    memset(p, 0, sizeof *p);
    p->active = active;
    p->color = color;
    p->yaw = g->spawn_yaw;
    vec3 offset = v3_scale(right_of(g->spawn_yaw), i == 0 ? 0.0f : 1.4f);
    p->pos = v3_add(g->spawn, offset);
    float y;
    if (collision_ground(g->col, p->pos.x, p->pos.z, p->pos.y + 2.0f, p->pos.y - 4.0f, &y, NULL))
        p->pos.y = y;
    else
        p->pos = g->spawn;
    p->cam_dist = 2.4f;
}

void game_init(Game *g, Collision *col, int screen_w, int screen_h) {
    memset(g, 0, sizeof *g);
    g->col = col;
    g->screen_w = screen_w;
    g->screen_h = screen_h;
    if (!find_spawn(g, &g->spawn)) {
        vec3 c = v3_scale(v3_add(col->bounds_min, col->bounds_max), 0.5f);
        g->spawn = v3(c.x, col->bounds_max.y, c.z);
    }
    g->spawn_yaw = 0.0f;
    g->players[0].color = v3(0.30f, 0.42f, 0.70f);   /* jogador 1: azul */
    g->players[1].color = v3(0.75f, 0.25f, 0.22f);   /* jogador 2: vermelho */
    g->players[0].active = 1;
    spawn_player(g, 0);
    spawn_player(g, 1);
}

static void add_impact(Game *g, vec3 pos, vec3 normal) {
    Impact *im = &g->impacts[g->next_impact];
    g->next_impact = (g->next_impact + 1) % MAX_IMPACTS;
    im->pos = pos;
    im->normal = normal;
    im->life = 6.0f;
}

/* Direcao para onde a camera olha (inclui a inclinacao) */
static vec3 view_dir(const Player *p) {
    float yaw = p->yaw + p->look_x * (1.0f - p->aim_blend) * 0.9f;
    float pitch = lerpf(-0.18f + p->look_y * 0.5f, p->aim_pitch, p->aim_blend);
    vec3 f = forward_of(yaw);
    return v3_norm(v3(f.x * cosf(pitch), sinf(pitch), f.z * cosf(pitch)));
}

static vec3 camera_pivot(const Player *p) {
    float side = lerpf(0.45f, 0.55f, p->aim_blend);
    float height = lerpf(1.55f, 1.6f, p->aim_blend);
    return v3_add(v3_add(p->pos, v3(0, height, 0)), v3_scale(right_of(p->yaw), side));
}

static void shoot(Game *g, Player *p) {
    vec3 pivot = camera_pivot(p);
    vec3 dir = view_dir(p);
    vec3 eye = v3_sub(pivot, v3_scale(dir, p->cam_dist));
    float t;
    vec3 n;
    /* raio sai da camera, passando pela mira no centro da tela */
    if (collision_raycast(g->col, eye, dir, SHOT_RANGE, &t, &n)) {
        if (v3_dot(n, dir) > 0) n = v3_scale(n, -1);
        add_impact(g, v3_add(eye, v3_scale(dir, t)), n);
    }
    p->shoot_cooldown = SHOOT_INTERVAL;
    p->muzzle_flash = 0.06f;
}

static void move_player(Game *g, Player *p, vec3 delta, float dt) {
    Collision *c = g->col;
    /* horizontal, em passos pequenos para nao atravessar paredes finas */
    float dist = v3_len(delta);
    int steps = (int)(dist / (PLAYER_RADIUS * 0.5f)) + 1;
    vec3 step = v3_scale(delta, 1.0f / (float)steps);
    for (int i = 0; i < steps; i++) {
        vec3 np = v3_add(p->pos, step);
        /* nao sobe em degrau mais alto que STEP_HEIGHT nem cai em buraco sem chao */
        float gy;
        if (collision_ground(c, np.x, np.z, np.y + STEP_HEIGHT, np.y - 50.0f, &gy, NULL) && gy > p->pos.y + STEP_HEIGHT)
            break;
        /* esferas na altura da canela, do quadril e do peito */
        for (int k = 0; k < 3; k++) {
            float h = (k == 0) ? STEP_HEIGHT + PLAYER_RADIUS : (k == 1 ? 1.0f : 1.45f);
            vec3 s = v3(np.x, np.y + h, np.z);
            collision_push_sphere(c, &s, PLAYER_RADIUS);
            np.x = s.x;
            np.z = s.z;
        }
        p->pos.x = np.x;
        p->pos.z = np.z;
    }

    /* vertical */
    float ground;
    vec3 gn;
    int has_ground = collision_ground(c, p->pos.x, p->pos.z, p->pos.y + STEP_HEIGHT, p->pos.y - 50.0f, &ground, &gn);
    if (p->grounded && has_ground && p->pos.y - ground < STEP_HEIGHT + 0.05f) {
        p->pos.y = ground;           /* gruda no chao em descidas e degraus */
        p->vel_y = 0;
    } else {
        p->vel_y -= GRAVITY * dt;
        p->pos.y += p->vel_y * dt;
        p->grounded = 0;
        if (has_ground && p->pos.y <= ground) {
            p->pos.y = ground;
            p->vel_y = 0;
            p->grounded = 1;
        }
    }
    /* caiu para fora do mapa: volta para o inicio */
    if (p->pos.y < c->bounds_min.y - 10.0f) {
        int idx = (int)(p - g->players);
        spawn_player(g, idx);
        p->grounded = 1;
    }
}

static void update_player(Game *g, Player *p, const Pad *pad, float dt) {
    if (p->shoot_cooldown > 0) p->shoot_cooldown -= dt;
    if (p->muzzle_flash > 0) p->muzzle_flash -= dt;

    int want_aim = pad->lt > 0.4f || (pad->buttons & PAD_LB);
    vec3 delta = v3(0, 0, 0);

    if (p->quickturn_t > 0) {
        /* giro rapido de 180 graus (para tras + B) */
        p->quickturn_t -= dt;
        float k = 1.0f - clampf(p->quickturn_t / QUICKTURN_TIME, 0, 1);
        p->yaw = p->quickturn_yaw0 + PI_F * k;
        want_aim = 0;
    } else if (want_aim) {
        /* mirando: parado, analogico esquerdo ou direito move a mira */
        float ax = pad->lx + pad->rx, ay = pad->ly + pad->ry;
        p->yaw -= clampf(ax, -1, 1) * AIM_TURN_SPEED * dt;
        p->aim_pitch = clampf(p->aim_pitch + clampf(ay, -1, 1) * AIM_PITCH_SPEED * dt, -0.9f, 0.9f);
        if ((pad->rt > 0.5f || (pad->buttons & PAD_RB)) && p->shoot_cooldown <= 0 && p->aim_blend > 0.7f)
            shoot(g, p);
    } else {
        /* andar estilo tanque: cima/baixo anda, esquerda/direita gira */
        if (pad->ly < -0.6f && (pad->pressed & PAD_B)) {
            p->quickturn_t = QUICKTURN_TIME;
            p->quickturn_yaw0 = p->yaw;
        }
        p->yaw -= pad->lx * TURN_SPEED * dt;
        float speed = 0;
        if (pad->ly > 0.15f) speed = (pad->buttons & PAD_A) ? RUN_SPEED : WALK_SPEED;
        else if (pad->ly < -0.15f) speed = -BACK_SPEED;
        speed *= fabsf(pad->ly) > 0.15f ? fminf(fabsf(pad->ly) * 1.2f, 1.0f) : 0;
        delta = v3_scale(forward_of(p->yaw), speed * dt);
        p->walk_cycle += fabsf(speed) * dt * 2.0f;
        p->aim_pitch = lerpf(p->aim_pitch, 0.0f, fminf(dt * 6.0f, 1.0f));
    }
    p->aiming = want_aim;
    p->aim_blend = clampf(p->aim_blend + (want_aim ? dt : -dt) * 6.0f, 0, 1);

    /* analogico direito sem mirar: olha em volta e volta ao soltar */
    float tx = want_aim ? 0 : pad->rx, ty = want_aim ? 0 : pad->ry;
    float k = fminf(dt * 8.0f, 1.0f);
    p->look_x = lerpf(p->look_x, -tx, k);
    p->look_y = lerpf(p->look_y, ty, k);

    move_player(g, p, delta, dt);
}

static void separate_players(Game *g) {
    Player *a = &g->players[0], *b = &g->players[1];
    if (!a->active || !b->active) return;
    vec3 d = v3_sub(b->pos, a->pos);
    d.y = 0;
    float dist = v3_len(d), min = PLAYER_RADIUS * 2.0f;
    if (dist < min && fabsf(a->pos.y - b->pos.y) < PLAYER_HEIGHT) {
        vec3 n = dist > 1e-4f ? v3_scale(d, 1.0f / dist) : right_of(a->yaw);
        vec3 push = v3_scale(n, (min - dist) * 0.5f);
        a->pos = v3_sub(a->pos, push);
        b->pos = v3_add(b->pos, push);
    }
}

void game_update(Game *g, const Pad pads[MAX_PLAYERS], float dt) {
    if (dt > 0.05f) dt = 0.05f;   /* evita saltos se um quadro demorar */

    /* jogador 2 entra apertando START no segundo controle, sai com BACK */
    Player *p2 = &g->players[1];
    if (!p2->active && pads[1].connected && (pads[1].pressed & PAD_START)) {
        p2->active = 1;
        g->spawn = g->players[0].pos;
        g->spawn_yaw = g->players[0].yaw;
        spawn_player(g, 1);
        p2->grounded = 1;
    } else if (p2->active && (!pads[1].connected || (pads[1].pressed & PAD_BACK))) {
        p2->active = 0;
    }

    for (int i = 0; i < MAX_PLAYERS; i++)
        if (g->players[i].active) update_player(g, &g->players[i], &pads[i], dt);
    separate_players(g);

    for (int i = 0; i < MAX_IMPACTS; i++)
        if (g->impacts[i].life > 0) g->impacts[i].life -= dt;
}

void game_build_cameras(Game *g) {
    int split = g->players[1].active;
    g->num_views = split ? 2 : 1;
    for (int i = 0; i < g->num_views; i++) {
        Player *p = &g->players[i];
        Camera *cam = &g->cams[i];
        /* tela dividida em cima/embaixo: cada um fica com 1280x360, bem panoramico */
        cam->vp_x = 0;
        cam->vp_w = g->screen_w;
        cam->vp_h = split ? g->screen_h / 2 : g->screen_h;
        cam->vp_y = split ? i * (g->screen_h / 2) : 0;

        vec3 pivot = camera_pivot(p);
        vec3 dir = view_dir(p);
        float want = lerpf(2.4f, 1.15f, p->aim_blend);
        /* camera nao atravessa parede: encurta ate o ponto de colisao */
        float t;
        float maxd = want;
        if (collision_raycast(g->col, pivot, v3_scale(dir, -1), want + 0.3f, &t, NULL))
            maxd = fmaxf(t - 0.3f, 0.3f);
        float k = maxd < p->cam_dist ? 1.0f : 0.15f;   /* encurta na hora, volta devagar */
        p->cam_dist = lerpf(p->cam_dist, maxd, k);

        cam->eye = v3_sub(pivot, v3_scale(dir, p->cam_dist));
        cam->target = v3_add(pivot, v3_scale(dir, 10.0f));
        cam->view = m4_look_at(cam->eye, cam->target, v3(0, 1, 0));
        float aspect = (float)cam->vp_w / (float)cam->vp_h;
        /* mantem o campo de visao horizontal igual com ou sem divisao (~75 graus) */
        float hfov = lerpf(75.0f, 55.0f, p->aim_blend) * PI_F / 180.0f;
        float vfov = 2.0f * atanf(tanf(hfov * 0.5f) / aspect);
        cam->proj = m4_perspective(vfov, aspect, 0.1f, 250.0f);
        cam->view_proj = m4_mul(cam->proj, cam->view);
    }
}
