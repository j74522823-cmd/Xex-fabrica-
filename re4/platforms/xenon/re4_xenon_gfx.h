#pragma once

#ifdef __cplusplus
extern "C" {
#endif

// Direct Vulkan4Xenon renderer. This is a native renderer, not a GX compatibility layer.
int re4_xenon_gfx_init(void);
int re4_xenon_gfx_clear_frame(float r, float g, float b, float a);
void re4_xenon_gfx_shutdown(void);

#ifdef __cplusplus
}
#endif
