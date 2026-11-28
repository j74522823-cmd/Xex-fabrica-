/* game.h - logica do jogo, sem nada especifico de plataforma. */
#ifndef GAME_H
#define GAME_H

#include <stdint.h>
#include "collision.h"

/* Botoes (mesmos bits do XInput, para o 360 nao precisar converter) */
enum {
    PAD_DPAD_UP = 0x0001, PAD_DPAD_DOWN = 0x0002, PAD_DPAD_LEFT = 0x0004, PAD_DPAD_RIGHT = 0x0008,
    PAD_START = 0x0010, PAD_BACK = 0x0020, PAD_LTHUMB = 0x0040, PAD_RTHUMB = 0x0080,
    PAD_LB = 0x0100, PAD_RB = 0x0200, PAD_A = 0x1000, PAD_B = 0x2000, PAD_X = 0x4000, PAD_Y = 0x8000
};

typedef struct {
    int connected;
    float lx, ly, rx, ry;        /* -1..1, ja com zona morta */
    float lt, rt;                /* 0..1 */
    uint16_t buttons;
    uint16_t pressed;            /* botoes que desceram neste quadro */
} Pad;

#define MAX_PLAYERS 2
#define MAX_IMPACTS 32

typedef struct {
    int active;
    vec3 pos;                    /* pes */
    float yaw;                   /* frente = (sin yaw, 0, cos yaw) */
    float vel_y;
    int grounded;
    int aiming;
    float aim_pitch;
    float look_x, look_y;        /* olhada com o analogico direito (volta sozinha) */
    float quickturn_t;           /* > 0 durante o giro de 180 */
    float quickturn_yaw0;
    float shoot_cooldown;
    float muzzle_flash;
    float aim_blend;             /* 0 = camera normal, 1 = mirando */
    float cam_dist;              /* distancia atual da camera (encurta em paredes) */
    float walk_cycle;
    vec3 color;
} Player;

typedef struct {
    vec3 pos;
    vec3 normal;
    float life;
} Impact;

typedef struct {
    vec3 eye, target;
    mat4 view, proj, view_proj;
    int vp_x, vp_y, vp_w, vp_h;  /* viewport em pixels */
} Camera;

typedef struct {
    Collision *col;
    Player players[MAX_PLAYERS];
    Impact impacts[MAX_IMPACTS];
    int next_impact;
    vec3 spawn;
    float spawn_yaw;
    int screen_w, screen_h;
    Camera cams[MAX_PLAYERS];
    int num_views;
} Game;

void game_init(Game *g, Collision *col, int screen_w, int screen_h);
void game_update(Game *g, const Pad pads[MAX_PLAYERS], float dt);
/* Monta as cameras/viewports para o quadro atual (1 ou 2 visoes). */
void game_build_cameras(Game *g);

#endif
