/* render.h - interface de desenho. A unica implementacao e render_xsdk.c (Xbox 360). */
#ifndef RENDER_H
#define RENDER_H

#include <stdint.h>
#include "map.h"

int  render_init(const Map *map, int screen_w, int screen_h);
void render_shutdown(void);

void render_frame_begin(void);
void render_view_begin(int x, int y, int w, int h, const mat4 *view_proj, vec3 eye);
void render_map(void);
void render_box(const mat4 *model, vec3 color);       /* cubo unitario centrado na origem */
void render_text(int x, int y, float scale, uint32_t argb, const char *text);
void render_frame_end(void);

#endif
