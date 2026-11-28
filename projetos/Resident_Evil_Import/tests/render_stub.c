/* render_stub.c - render falso para compilar e contar draws no PC. */
#include "../src/render.h"
#include <stdio.h>
int stub_draws, stub_boxes, stub_views;
int  render_init(const Map *m, int w, int h) { (void)m; (void)w; (void)h; return 1; }
void render_shutdown(void) {}
void render_frame_begin(void) { stub_draws = stub_boxes = stub_views = 0; }
static const Map *g; void stub_set_map(const Map *m) { g = m; }
void render_view_begin(int x, int y, int w, int h, const mat4 *vp, vec3 e) { (void)x;(void)y;(void)w;(void)h;(void)vp;(void)e; stub_views++; }
void render_map(void) { stub_draws += g->num_batches; }
void render_box(const mat4 *m, vec3 c) { (void)m; (void)c; stub_draws++; stub_boxes++; }
void render_text(int x, int y, float s, uint32_t a, const char *t) { (void)x;(void)y;(void)s;(void)a;(void)t; }
void render_frame_end(void) {}
