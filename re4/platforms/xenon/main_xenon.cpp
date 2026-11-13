// Xbox 360 entry point for the RE4 port: brings Aurora up (GX/Vulkan, DVD image, input) and then runs the game's own
// main (src/game/main.cpp, compiled with -Dmain=re4_game_main), which boots the SDK and runs the frame loop itself.
#include <aurora/aurora.h>
#include <aurora/dvd.h>
#include <aurora/main.h>   // defines main -> aurora_main
#include <xsdk/log.h>
#include <stdio.h>

// Independent file diagnostics; write both names so they are easy to find on different launch setups.
static void re4_diag_write_file(const char* path, const char* message)
{
    FILE* f = fopen(path, "ab");
    if (f) {
        fputs(message ? message : "(null)", f);
        fputc(10, f);
        fflush(f);
        fclose(f);
    }
}

extern "C" void re4_diag_write(const char* message)
{
    re4_diag_write_file("game:\\re4_boot.log", message);
    re4_diag_write_file("game:\\re4.log", message);
}

// Construtor estático: roda antes do main(), junto com os inicializadores globais.
struct RE4EarlyBootMark {
    RE4EarlyBootMark() { re4_diag_write("STATIC: construtores globais rodando"); }
};
static RE4EarlyBootMark g_re4EarlyBootMark;

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
    // First instruction-level diagnostic in the Xenon/Aurora entry point.
    re4_diag_write("MAIN_XENON: entry point reached");
    xsdk_log_write("re4: started");
    re4_diag_write("MAIN_XENON: before aurora_initialize");
    xsdk_log_write("re4: before aurora_initialize");

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
    re4_diag_write("AURORA: initialize returned");
    xsdk_log_write("re4: aurora up");

    re4_diag_write("DVD: before aurora_dvd_open");
    xsdk_log_write("re4: before aurora_dvd_open");
    if (!aurora_dvd_open(RE4_DISC_PATH)) {
        // Do not enter the original game with an unavailable disc. Its startup immediately
        // initializes DVD tables and reads mandatory files; continuing here turns a simple
        // mount/path problem into a later black-screen crash with a misleading location.
        re4_diag_write("FATAL: DVD image open failed; game entry skipped");
        xsdk_log_write("re4: FATAL: cannot open disc image %s; skipping game entry", RE4_DISC_PATH);
        aurora_shutdown();
        return 2;
    }
    re4_diag_write("DVD: image opened");
    xsdk_log_write("re4: disc image opened");

    re4_diag_write("VIDEO: before first aurora_begin_frame");
    xsdk_log_write("re4: before first aurora_begin_frame");
    aurora_begin_frame();
    re4_diag_write("GAME_MAIN: immediately before re4_game_main call");
    xsdk_log_write("re4: before re4_game_main");
    int r = re4_game_main();
    re4_diag_write("GAME_MAIN: re4_game_main returned");
    xsdk_log_write("re4: re4_game_main returned");
    aurora_shutdown();
    return r;
}
