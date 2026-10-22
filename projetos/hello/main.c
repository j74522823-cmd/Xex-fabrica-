// hello: the log, the display and a controller. The screen's colour follows the sticks and triggers, and A rumbles.
// It runs until Back, or until the title is left through the Guide's Xbox Home.

#include <stdbool.h>
#include <stdint.h>

#include "xsdk/gpu.h"
#include "xsdk/kernel.h"
#include "xsdk/log.h"
#include "xsdk/present.h"
#include "xsdk/splash.h"
#include "xsdk/texture.h"

enum {
	SPLASH_MS = 2000,
	BUFFERS = 2,
	SWAP_INTERVAL = 1,
	// The Guide's first opening held a frame up 2.7 s (docs/HARDWARE.md, "The Guide, milestone 37").
	BEGIN_TIMEOUT_MS = 5000,
	FENCE_TIMEOUT_MS = 1000,
	RUMBLE_SPEED = 0x8000,
	MAX_WIDTH = 1280,
};

static void check_first_frame(uint32_t address, uint32_t width, uint32_t height, uint32_t argb);
static void log_checks(void);

// The left stick's x sets red and the right stick's y green, each 0 at one end and 255 at the other; the right trigger
// sets blue, and the left trigger dims all three.
static uint32_t colour_of(const INPUT_GAMEPAD *pad)
{
	const uint32_t dim = 255 - pad->left_trigger;
	const uint32_t red = (uint32_t)(pad->thumb_lx + 32768) >> 8;
	const uint32_t green = (uint32_t)(pad->thumb_ry + 32768) >> 8;
	const uint32_t blue = pad->right_trigger;
	return 0xFF000000 | red * dim / 255 << 16 | green * dim / 255 << 8 | blue * dim / 255;
}

static void set_rumble(bool on)
{
	const INPUT_VIBRATION vibration = { on ? RUMBLE_SPEED : 0, on ? RUMBLE_SPEED : 0 };
	const uint32_t result = XamInputSetState(0, 0, &vibration);
	if (result != ERROR_SUCCESS)
		xsdk_log_write("hello: XamInputSetState failed: 0x%08X", (unsigned)result);
}

// Each frame reads controller 1, then resolves eDRAM into the next front buffer and shows it. A resolve copies eDRAM,
// then clears it, so each frame shows the colour the frame before cleared to.
static void run(uint32_t width, uint32_t height)
