#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "calculadora_shaders.h"
#include "xsdk/gpu.h"
#include "xsdk/kernel.h"
#include "xsdk/log.h"
#include "xsdk/present.h"
#include "xsdk/shader.h"

enum {
    BUFFERS = 2,
    SWAP_INTERVAL = 1,
    FRAME_TIMEOUT_MS = 5000,
    MAX_VERTICES = 12000,
    VERTEX_FLOATS = 5,
    VERTEX_BYTES = VERTEX_FLOATS * 4,
    CLEAR_ARGB = 0xFF07110D,
};

typedef struct {
    float x, y, r, g, b;
} Vertex;

static Vertex cpu_vertices[MAX_VERTICES];
static uint32_t upload_words[MAX_VERTICES * VERTEX_FLOATS];
static volatile uint32_t *gpu_vertices;
static uint32_t vertex_count;
static uint32_t screen_width, screen_height;
static float ui_scale = 1.0f, ui_offset_x, ui_offset_y;

static const XsdkVertexElement vertex_layout[] = {
    { .usage = XSDK_USAGE_POSITION, .format = XSDK_VERTEX_FLOAT2, .offset_bytes = 0 },
    { .usage = XSDK_USAGE_COLOR, .format = XSDK_VERTEX_FLOAT3, .offset_bytes = 8 },
};

static void add_vertex(float x, float y, uint32_t color)
{
    if (vertex_count >= MAX_VERTICES)
        return;

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
    w *= ui_scale;
    h *= ui_scale;
    const float x2 = x + w, y2 = y + h;
    add_vertex(x, y, color);   add_vertex(x2, y, color);  add_vertex(x2, y2, color);
    add_vertex(x, y, color);   add_vertex(x2, y2, color); add_vertex(x, y2, color);
}

static void glyph_rows(char ch, uint8_t rows[7])
{
    static const uint8_t digits[10][7] = {
        {14,17,19,21,25,17,14}, {4,12,4,4,4,4,14}, {14,17,1,2,4,8,31},
        {30,1,1,14,1,1,30}, {2,6,10,18,31,2,2}, {31,16,16,30,1,1,30},
        {6,8,16,30,17,17,14}, {31,1,2,4,8,8,8}, {14,17,17,14,17,17,14},
        {14,17,17,15,1,2,12}
    };
    static const uint8_t blank[7] = {0,0,0,0,0,0,0};
    const uint8_t *src = blank;

    if (ch >= '0' && ch <= '9') src = digits[ch - '0'];
    else {
        static const uint8_t plus[7]  = {0,4,4,31,4,4,0};
        static const uint8_t minus[7] = {0,0,0,31,0,0,0};
        static const uint8_t mult[7]  = {0,17,10,4,10,17,0};
        static const uint8_t divi[7]  = {1,2,4,8,16,0,0};
        static const uint8_t equal[7] = {0,31,0,31,0,0,0};
        static const uint8_t c[7]     = {14,17,16,16,16,17,14};
        static const uint8_t a[7]     = {14,17,17,31,17,17,17};
        static const uint8_t l[7]     = {16,16,16,16,16,16,31};
        static const uint8_t e[7]     = {31,16,16,30,16,16,31};
        static const uint8_t r[7]     = {30,17,17,30,20,18,17};
        switch (ch) {
        case '+': src = plus; break;
        case '-': src = minus; break;
        case '*': src = mult; break;
        case '/': src = divi; break;
        case '=': src = equal; break;
        case 'C': src = c; break;
        case 'A': src = a; break;
        case 'L': src = l; break;
        case 'E': src = e; break;
        case 'R': src = r; break;
        default: break;
        }
    }
    memcpy(rows, src, 7);
}

static void draw_text(int x, int y, int scale, uint32_t color, const char *text)
{
    for (; *text; ++text, x += scale * 6) {
        uint8_t rows[7];
        glyph_rows(*text, rows);
        for (int row = 0; row < 7; ++row)
            for (int col = 0; col < 5; ++col)
                if (rows[row] & (1u << (4 - col)))
                    rect((float)(x + col * scale), (float)(y + row * scale),
                         (float)scale, (float)scale, color);
    }
}

static int64_t current_value;
static int64_t stored_value;
static char pending_operator;
static bool entering_new_value = true;
static bool calculation_error;
static unsigned selected_key;

static void clear_calculator(void)
{
    current_value = 0;
    stored_value = 0;
    pending_operator = 0;
    entering_new_value = true;
    calculation_error = false;
}

static void choose_key(char key)
{
    if (key == 'C') {
        clear_calculator();
        return;
    }
    if (calculation_error)
        clear_calculator();

    if (key >= '0' && key <= '9') {
        if (entering_new_value) {
            current_value = 0;
            entering_new_value = false;
        }
        if (current_value <= 999999999)
            current_value = current_value * 10 + (key - '0');
        return;
    }

    if (key == '=') {
        if (!pending_operator)
            return;
        switch (pending_operator) {
        case '+': current_value = stored_value + current_value; break;
        case '-': current_value = stored_value - current_value; break;
        case '*': current_value = stored_value * current_value; break;
        case '/':
            if (current_value == 0) {
                calculation_error = true;
                pending_operator = 0;
                return;
            }
            current_value = stored_value / current_value;
            break;
        }
        pending_operator = 0;
        entering_new_value = true;
        return;
    }

    if (key == '+' || key == '-' || key == '*' || key == '/') {
        stored_value = current_value;
        pending_operator = key;
        entering_new_value = true;
    }
}

static void backspace_or_clear(void)
{
    if (calculation_error) {
        clear_calculator();
        return;
    }
    current_value /= 10;
    entering_new_value = false;
}

static void render_frame(const XsdkShader *vs, const XsdkShader *ps, uint32_t address)
{
    vertex_count = 0;
    rect(0, 0, (float)screen_width, (float)screen_height, CLEAR_ARGB);

    draw_text(580, 42, 5, 0xFF49FF91, "CALC");
    const float panel_x = 360.0f;
    rect(panel_x, 105, 560, 105, 0xFF10251A);
    rect(panel_x + 4, 109, 552, 97, 0xFF0B1911);

    char display[32];
    if (calculation_error)
        snprintf(display, sizeof display, "ERR");
    else
        snprintf(display, sizeof display, "%lld", (long long)current_value);
    draw_text((int)panel_x + 28, 135, 6, 0xFFE6FFF0, display);
    if (pending_operator) {
        char op[2] = { pending_operator, 0 };
        draw_text((int)panel_x + 500, 140, 5, 0xFF49FF91, op);
    }

    static const char keys[16] = {
        '7','8','9','/','4','5','6','*','1','2','3','-','C','0','=','+'
    };
    const float key_w = 130.0f, key_h = 78.0f, gap = 13.0f;
    const float start_x = 360.0f;
    const float start_y = 235.0f;

    for (unsigned i = 0; i < 16; ++i) {
        const unsigned row = i / 4, col = i % 4;
        const float x = start_x + col * (key_w + gap);
        const float y = start_y + row * (key_h + gap);
        const bool selected = i == selected_key;
        rect(x, y, key_w, key_h, selected ? 0xFF49FF91 : 0xFF1A3024);
        rect(x + 3, y + 3, key_w - 6, key_h - 6,
             selected ? 0xFF17452C : 0xFF102019);
        char label[2] = { keys[i], 0 };
        const uint32_t label_color = selected ? 0xFFFFFFFF : 0xFFB8DCC5;
        draw_text((int)(x + key_w / 2 - 15), (int)(y + key_h / 2 - 21), 6, label_color, label);
    }

    memcpy(upload_words, cpu_vertices, vertex_count * sizeof(Vertex));
    const uint32_t words = vertex_count * VERTEX_FLOATS;
    for (uint32_t i = 0; i < words; ++i)
        gpu_vertices[i] = upload_words[i];
    xsdk_gpu_invalidate(xsdk_gpu_address(gpu_vertices), vertex_count * VERTEX_BYTES);

    xsdk_gpu_set_target(screen_width, screen_height);
    xsdk_gpu_set_shaders(vs, ps);
    xsdk_gpu_set_vertices(0, xsdk_gpu_address(gpu_vertices), vertex_count * VERTEX_BYTES);
    xsdk_gpu_draw(XSDK_PRIMITIVE_TRIANGLE_LIST, vertex_count);
    xsdk_gpu_resolve(address, screen_width, screen_height, CLEAR_ARGB);
    xsdk_present_end();
}

int main(void)
{
    xsdk_log_write("calculadora: D-pad move, A seleciona, B apaga, Back sai");
    if (!NT_SUCCESS(xsdk_gpu_open())) {
        xsdk_log_write("calculadora: falha ao abrir GPU");
        return 1;
    }

    XsdkShader vertex_shader = { .microcode = NULL };
    XsdkShader pixel_shader = { .microcode = NULL };
    NTSTATUS status = xsdk_shader_load(&vertex_shader, calc_vert.container,
                                       calc_vert.container_bytes);
    if (NT_SUCCESS(status))
        status = xsdk_shader_load(&pixel_shader, calc_frag.container,
                                  calc_frag.container_bytes);
    if (NT_SUCCESS(status))
        status = xsdk_shader_set_vertex_layout(&vertex_shader, vertex_layout, 2,
                                               (const uint32_t[]){ VERTEX_BYTES });
    if (!NT_SUCCESS(status)) {
        xsdk_log_write("calculadora: falha ao carregar shaders: 0x%08X", (unsigned)status);
        return 1;
    }

    gpu_vertices = xsdk_gpu_alloc(MAX_VERTICES * VERTEX_BYTES);
    if (!gpu_vertices) {
        xsdk_log_write("calculadora: sem memoria para vertices");
        return 1;
    }

    status = xsdk_present_open(XSDK_DISPLAY_720P, BUFFERS, SWAP_INTERVAL,
                               &screen_width, &screen_height);
    if (!NT_SUCCESS(status)) {
        xsdk_log_write("calculadora: falha ao abrir display: 0x%08X", (unsigned)status);
        return 1;
    }

    /* Layout em coordenadas logicas 1280x720, ajustado ao modo real do display. */
    const float sx = (float)screen_width / 1280.0f;
    const float sy = (float)screen_height / 720.0f;
    ui_scale = sx < sy ? sx : sy;
    ui_offset_x = ((float)screen_width - 1280.0f * ui_scale) * 0.5f;
    ui_offset_y = ((float)screen_height - 720.0f * ui_scale) * 0.5f;
    xsdk_log_write("calculadora: display %ux%u, escala UI %.3f", screen_width, screen_height, ui_scale);

    uint16_t previous_buttons = 0;
    for (;;) {
        INPUT_STATE input = { 0 };
        if (XamInputGetState(0, 0, &input) != ERROR_SUCCESS)
            input = (INPUT_STATE){ 0 };
        const uint16_t pressed = input.gamepad.buttons & (uint16_t)~previous_buttons;
        previous_buttons = input.gamepad.buttons;

        if (pressed & INPUT_GAMEPAD_BACK)
            break;
        if (pressed & INPUT_GAMEPAD_DPAD_UP)
            selected_key = (selected_key + 12) % 16;
        if (pressed & INPUT_GAMEPAD_DPAD_DOWN)
            selected_key = (selected_key + 4) % 16;
        if (pressed & INPUT_GAMEPAD_DPAD_LEFT)
            selected_key = (selected_key + 15) % 16;
        if (pressed & INPUT_GAMEPAD_DPAD_RIGHT)
            selected_key = (selected_key + 1) % 16;
        if (pressed & INPUT_GAMEPAD_A) {
            static const char keys[16] = {
                '7','8','9','/','4','5','6','*','1','2','3','-','C','0','=','+'
            };
            choose_key(keys[selected_key]);
        }
        if (pressed & INPUT_GAMEPAD_B)
            backspace_or_clear();

        uint32_t address;
        status = xsdk_present_begin(&address, FRAME_TIMEOUT_MS);
        if (!NT_SUCCESS(status)) {
            xsdk_log_write("calculadora: falha ao iniciar frame: 0x%08X", (unsigned)status);
            break;
        }

        status = xsdk_gpu_wait(xsdk_gpu_fence(), FRAME_TIMEOUT_MS);
        if (!NT_SUCCESS(status)) {
            xsdk_log_write("calculadora: GPU nao terminou o frame anterior: 0x%08X", (unsigned)status);
            break;
        }
        render_frame(&vertex_shader, &pixel_shader, address);
    }

    xsdk_present_close();
    xsdk_gpu_free(gpu_vertices);
    xsdk_shader_free(&pixel_shader);
    xsdk_shader_free(&vertex_shader);
    xsdk_gpu_close();
    xsdk_log_write("calculadora: encerrada");
    return 0;
}
