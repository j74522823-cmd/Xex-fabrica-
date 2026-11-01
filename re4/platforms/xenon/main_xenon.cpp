// Xbox 360 entry point for the RE4 port: brings Aurora up (GX/Vulkan, DVD image, input) and then runs the game's own
// main (src/game/main.cpp, compiled with -Dmain=re4_game_main), which boots the SDK and runs the frame loop itself.
#include <aurora/aurora.h>
#include <aurora/dvd.h>
#include <aurora/main.h>   // defines main -> aurora_main
#include <xsdk/log.h>
#include <stdio.h>

extern int re4_game_main();

// One call per presented frame (VISetNextFrameBuffer in os_compat.cpp).
void re4_frame_boundary()
{
    aurora_end_frame();
    aurora_update();
    aurora_begin_frame();
}

static void LogCb(AuroraLogLevel level, const char* module, const char* message, unsigned int)
{
    xsdk_log_write("[aurora %d] %s: %s", (int)level, module, message);
}

// Where the debug disc image (disc 1) has to be on the console / HDD.
#ifndef RE4_DISC_PATH
#define RE4_DISC_PATH "game:\\re4.iso"
#endif

int main(int argc, char* argv[])
{
    xsdk_log_write("re4: started");

    AuroraConfig cfg = {};
    cfg.appName = "RE4";
    cfg.desiredBackend = BACKEND_VULKAN;
    cfg.msaa = 1;
    cfg.vsync = true;
    cfg.maxTextureAnisotropy = 1;
    cfg.logCallback = LogCb;
    cfg.logLevel = LOG_INFO;
    cfg.mem1Size = MEM1_DEFAULT_SIZE;
    cfg.mem2Size = ARAM_DEFAULT_SIZE;
    aurora_initialize(argc, argv, &cfg);
    xsdk_log_write("re4: aurora up");

    if (!aurora_dvd_open(RE4_DISC_PATH)) {
        xsdk_log_write("re4: cannot open disc image " RE4_DISC_PATH);
    }

    aurora_begin_frame();
    int r = re4_game_main();
    aurora_shutdown();
    return r;
}
