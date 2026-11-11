#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "pong_shaders.h"
#include "xsdk/gpu.h"
#include "xsdk/kernel.h"
#include "xsdk/log.h"
#include "xsdk/present.h"
#include "xsdk/shader.h"

enum {
    BUFFERS = 2,
    SWAP_INTERVAL = 1,
    FRAME_TIMEOUT_MS = 5000,
    MAX_VERTICES = 4096,
    VERTEX_FLOATS = 5,
    VERTEX_BYTES = VERTEX_FLOATS * 4,
    CLEAR_ARGB = 0xFF06130F,
};

typedef struct { float x, y, r, g, b; } Vertex;
static Vertex cpu_vertices[MAX_VERTICES];
static uint32_t upload_words[MAX_VERTICES * VERTEX_FLOATS];
static volatile uint32_t *gpu_vertices;
static uint32_t vertex_count, screen_width, screen_height;
static float ui_scale = 1.0f, ui_offset_x, ui_offset_y;

static const XsdkVertexElement vertex_layout[] = {
    { .usage = XSDK_USAGE_POSITION, .format = XSDK_VERTEX_FLOAT2, .offset_bytes = 0 },
    { .usage = XSDK_USAGE_COLOR, .format = XSDK_VERTEX_FLOAT3, .offset_bytes = 8 },
};

static void add_vertex(float x, float y, uint32_t color)
{
    if (vertex_count >= MAX_VERTICES) return;
    Vertex *v = &cpu_vertices[vertex_count++];
    v->x = x * 2.0f / (float)screen_width - 1.0f;
    v->y = 1.0f - y * 2.0f / (float)screen_height;
    v->r = (float)((color >> 16) & 255) / 255.0f;
    v->g = (float)((color >> 8) & 255) / 255.0f;
    v->b = (float)(color & 255) / 255.0f;
}

static void rect(float x, float y, float w, float h, uint32_t color)
{
    x = x * ui_scale + ui_offset_x;
    y = y * ui_scale + ui_offset_y;
    w *= ui_scale; h *= ui_scale;
    float x2 = x + w, y2 = y + h;
    add_vertex(x,y,color); add_vertex(x2,y,color); add_vertex(x2,y2,color);
    add_vertex(x,y,color); add_vertex(x2,y2,color); add_vertex(x,y2,color);
}

static void draw_digit(int x, int y, int scale, unsigned digit, uint32_t color)
{
    static const uint8_t glyph[10][7] = {
        {14,17,19,21,25,17,14},{4,12,4,4,4,4,14},{14,17,1,2,4,8,31},
        {30,1,1,14,1,1,30},{2,6,10,18,31,2,2},{31,16,16,30,1,1,30},
        {6,8,16,30,17,17,14},{31,1,2,4,8,8,8},{14,17,17,14,17,17,14},
        {14,17,17,15,1,2,12}
    };
    if (digit > 9) return;
    for (int row=0; row<7; ++row)
        for (int col=0; col<5; ++col)
            if (glyph[digit][row] & (1u << (4-col)))
                rect((float)(x+col*scale),(float)(y+row*scale),
                     (float)scale,(float)scale,color);
}

static float player_y = 300.0f, cpu_y = 300.0f;
static float ball_x = 640.0f, ball_y = 360.0f, ball_vx = 7.0f, ball_vy = 3.0f;
static unsigned player_score, cpu_score;
static bool game_over;

static void reset_ball(float direction)
{
    ball_x = 640.0f; ball_y = 360.0f;
    ball_vx = 7.0f * direction; ball_vy = (ball_vy < 0 ? -3.5f : 3.5f);
}

static void reset_game(void)
{
    player_score = cpu_score = 0;
    player_y = cpu_y = 300.0f;
    ball_vy = 3.5f;
    game_over = false;
    reset_ball(1.0f);
}

static void update_game(uint16_t buttons)
{
    if (game_over) {
        if (buttons & INPUT_GAMEPAD_A) reset_game();
        return;
    }

    if (buttons & INPUT_GAMEPAD_DPAD_UP) player_y -= 8.0f;
    if (buttons & INPUT_GAMEPAD_DPAD_DOWN) player_y += 8.0f;
    if (player_y < 35.0f) player_y = 35.0f;
    if (player_y > 565.0f) player_y = 565.0f;

    /* Adversario simples: acompanha a bola com velocidade limitada. */
    float cpu_center = cpu_y + 45.0f;
    if (cpu_center < ball_y - 12.0f) cpu_y += 5.0f;
    else if (cpu_center > ball_y + 12.0f) cpu_y -= 5.0f;
    if (cpu_y < 35.0f) cpu_y = 35.0f;
    if (cpu_y > 565.0f) cpu_y = 565.0f;

    ball_x += ball_vx;
    ball_y += ball_vy;
    if (ball_y < 18.0f || ball_y > 702.0f) ball_vy = -ball_vy;

    if (ball_vx < 0.0f && ball_x < 92.0f && ball_x > 65.0f &&
        ball_y + 10.0f > player_y && ball_y - 10.0f < player_y + 90.0f) {
        ball_vx = -ball_vx * 1.04f;
        ball_vy += (ball_y - (player_y + 45.0f)) * 0.055f;
    }
    if (ball_vx > 0.0f && ball_x > 1188.0f && ball_x < 1215.0f &&
        ball_y + 10.0f > cpu_y && ball_y - 10.0f < cpu_y + 90.0f) {
        ball_vx = -ball_vx * 1.04f;
        ball_vy += (ball_y - (cpu_y + 45.0f)) * 0.045f;
    }

    if (ball_x < 0.0f) {
        ++cpu_score; reset_ball(1.0f);
    } else if (ball_x > 1280.0f) {
        ++player_score; reset_ball(-1.0f);
    }
    if (player_score >= 5 || cpu_score >= 5) game_over = true;
}

static void render_frame(const XsdkShader *vs, const XsdkShader *ps, uint32_t address)
{
    vertex_count = 0;
    rect(0,0,1280,720,CLEAR_ARGB);
    /* Linha central pontilhada e moldura. */
    for (int y=20; y<700; y+=34) rect(637,(float)y,6,18,0xFF24523A);
    rect(35,18,1210,3,0xFF24523A);
    rect(35,699,1210,3,0xFF24523A);

    rect(72,player_y,18,90,0xFF54FF9A);
    rect(1190,cpu_y,18,90,0xFF54FF9A);
    rect(ball_x-10,ball_y-10,20,20,0xFFFFFFFF);

    draw_digit(590,48,8,player_score,0xFFB8FFD0);
    draw_digit(660,48,8,cpu_score,0xFFB8FFD0);

    if (game_over) {
        /* Faixa de fim de partida; A reinicia. */
        rect(360,290,560,140,0xFF10291D);
        rect(370,300,540,120,0xFF1C4A31);
        for (int i=0;i<5;i++) rect(430.0f+i*85.0f,350,36,12,0xFF54FF9A);
    }

    memcpy(upload_words,cpu_vertices,vertex_count*sizeof(Vertex));
    uint32_t words=vertex_count*VERTEX_FLOATS;
    for(uint32_t i=0;i<words;i++) gpu_vertices[i]=upload_words[i];
    xsdk_gpu_invalidate(xsdk_gpu_address(gpu_vertices),vertex_count*VERTEX_BYTES);
    xsdk_gpu_set_target(screen_width,screen_height);
    xsdk_gpu_set_shaders(vs,ps);
    xsdk_gpu_set_vertices(0,xsdk_gpu_address(gpu_vertices),vertex_count*VERTEX_BYTES);
    xsdk_gpu_draw(XSDK_PRIMITIVE_TRIANGLE_LIST,vertex_count);
    xsdk_gpu_resolve(address,screen_width,screen_height,CLEAR_ARGB);
    xsdk_present_end();
}

int main(void)
{
    xsdk_log_write("JOJO PONG: D-pad move, A reinicia apos fim, Back sai");
    if (!NT_SUCCESS(xsdk_gpu_open())) { xsdk_log_write("JOJO PONG: falha GPU"); return 1; }

    XsdkShader vs={.microcode=NULL}, ps={.microcode=NULL};
    NTSTATUS status=xsdk_shader_load(&vs,pong_vert.container,pong_vert.container_bytes);
    if(NT_SUCCESS(status)) status=xsdk_shader_load(&ps,pong_frag.container,pong_frag.container_bytes);
    if(NT_SUCCESS(status)) status=xsdk_shader_set_vertex_layout(&vs,vertex_layout,2,(const uint32_t[]){VERTEX_BYTES});
    if(!NT_SUCCESS(status)){xsdk_log_write("JOJO PONG: falha shaders 0x%08X",(unsigned)status);return 1;}

    gpu_vertices=xsdk_gpu_alloc(MAX_VERTICES*VERTEX_BYTES);
    if(!gpu_vertices){xsdk_log_write("JOJO PONG: sem memoria");return 1;}
    status=xsdk_present_open(XSDK_DISPLAY_720P,BUFFERS,SWAP_INTERVAL,&screen_width,&screen_height);
    if(!NT_SUCCESS(status)){xsdk_log_write("JOJO PONG: falha display 0x%08X",(unsigned)status);return 1;}

    float sx=(float)screen_width/1280.0f, sy=(float)screen_height/720.0f;
    ui_scale=sx<sy?sx:sy;
    ui_offset_x=((float)screen_width-1280.0f*ui_scale)*0.5f;
    ui_offset_y=((float)screen_height-720.0f*ui_scale)*0.5f;
    xsdk_log_write("JOJO PONG: display %ux%u escala %.3f",screen_width,screen_height,ui_scale);

    reset_game();
    uint16_t previous=0;
    for(;;){
        INPUT_STATE input={0};
        if(XamInputGetState(0,0,&input)!=ERROR_SUCCESS) input=(INPUT_STATE){0};
        uint16_t held=input.gamepad.buttons;
        uint16_t pressed=held & (uint16_t)~previous;
        previous=held;
        if(pressed & INPUT_GAMEPAD_BACK) break;
        update_game(held);

        uint32_t address;
        status=xsdk_present_begin(&address,FRAME_TIMEOUT_MS);
        if(!NT_SUCCESS(status)){xsdk_log_write("JOJO PONG: falha frame 0x%08X",(unsigned)status);break;}
        status=xsdk_gpu_wait(xsdk_gpu_fence(),FRAME_TIMEOUT_MS);
        if(!NT_SUCCESS(status)){xsdk_log_write("JOJO PONG: timeout GPU 0x%08X",(unsigned)status);break;}
        render_frame(&vs,&ps,address);
    }

    xsdk_present_close();
    xsdk_gpu_free(gpu_vertices);
    xsdk_shader_free(&ps);
    xsdk_shader_free(&vs);
    xsdk_gpu_close();
    xsdk_log_write("JOJO PONG: encerrado");
    return 0;
}
