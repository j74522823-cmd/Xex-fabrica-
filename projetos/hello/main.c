#include <stdbool.h>
#include <stdint.h>
#include "xsdk/gpu.h"
#include "xsdk/kernel.h"
#include "xsdk/log.h"
#include "xsdk/present.h"

int main(void)
{
	uint32_t width = 0, height = 0;
	if (!NT_SUCCESS(xsdk_gpu_open()))
		return 1;
	if (!NT_SUCCESS(xsdk_present_open(XSDK_DISPLAY_720P, 2, 1, &width, &height)))
		return 1;
	xsdk_log_write("hello: display %ux%u", (unsigned)width, (unsigned)height);
	for (;;) {
		INPUT_STATE input = { 0 };
		if (XamInputGetState(0, 0, &input) != ERROR_SUCCESS)
			input = (INPUT_STATE){ 0 };
		if (input.gamepad.buttons & INPUT_GAMEPAD_BACK)
			break;
		uint32_t address;
		if (!NT_SUCCESS(xsdk_present_begin(&address, 5000)))
			break;
		uint32_t red = (uint32_t)(input.gamepad.thumb_lx + 32768) >> 8;
		uint32_t green = (uint32_t)(input.gamepad.thumb_ry + 32768) >> 8;
		uint32_t blue = input.gamepad.right_trigger;
		xsdk_gpu_resolve(address, width, height, 0xFF000000 | red << 16 | green << 8 | blue);
		xsdk_present_end();
	}
	xsdk_present_close();
	xsdk_gpu_close();
	xsdk_log_write("hello: done");
	return 0;
}
