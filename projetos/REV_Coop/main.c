#include <stdint.h>

#include "xsdk/kernel.h"
#include "xsdk/log.h"
#include "xsdk/thread.h"

enum {
    PLAYER_COUNT = 2,
    POLL_INTERVAL_MS = 100,
    POLL_COUNT = 300
};

static void poll_controller(
    uint32_t user,
    uint32_t *last_packet,
    int *connected
)
{
    INPUT_STATE state = {0};

    const uint32_t result = XamInputGetState(user, 0, &state);

    if (result == ERROR_SUCCESS)
    {
        if (!(*connected))
        {
            xsdk_log_write(
                "REV: PLAYER %u CONNECTED",
                (unsigned)(user + 1)
            );
            *connected = 1;
        }

        if (state.packet_number != *last_packet)
        {
            xsdk_log_write(
                "PLAYER %u | BUTTONS %04X | LX %d | LY %d | RX %d | RY %d | LT %u | RT %u",
                (unsigned)(user + 1),
                (unsigned)state.gamepad.buttons,
                (int)state.gamepad.thumb_lx,
                (int)state.gamepad.thumb_ly,
                (int)state.gamepad.thumb_rx,
                (int)state.gamepad.thumb_ry,
                (unsigned)state.gamepad.left_trigger,
                (unsigned)state.gamepad.right_trigger
            );

            *last_packet = state.packet_number;
        }
    }
    else if (*connected)
    {
        xsdk_log_write(
            "REV: PLAYER %u DISCONNECTED (0x%08X)",
            (unsigned)(user + 1),
            (unsigned)result
        );
        *connected = 0;
        *last_packet = UINT32_MAX;
    }
}

int main(void)
{
    xsdk_log_write("================================");
    xsdk_log_write("REV COOP BUILD 001");
    xsdk_log_write("Two-controller diagnostic started");
    xsdk_log_write("Polling for 30 seconds...");
    xsdk_log_write("================================");

    uint32_t packets[PLAYER_COUNT] = {
        UINT32_MAX, UINT32_MAX
    };

    int connected[PLAYER_COUNT] = {0, 0};

    for (int i = 0; i < POLL_COUNT; i++)
    {
        for (uint32_t user = 0; user < PLAYER_COUNT; user++)
        {
            poll_controller(user, &packets[user], &connected[user]);
        }

        const NTSTATUS sleep_status = xsdk_thread_sleep(POLL_INTERVAL_MS);
        if (!NT_SUCCESS(sleep_status))
        {
            xsdk_log_write(
                "REV: sleep failed: 0x%08X",
                (unsigned)sleep_status
            );
            break;
        }
    }

    for (uint32_t user = 0; user < PLAYER_COUNT; user++)
    {
        if (connected[user])
        {
            xsdk_log_write(
                "REV: PLAYER %u FINAL STATUS: CONNECTED",
                (unsigned)(user + 1)
            );
        }
        else
        {
            xsdk_log_write(
                "REV: PLAYER %u FINAL STATUS: NOT DETECTED",
                (unsigned)(user + 1)
            );
        }
    }

    xsdk_log_write("REV COOP BUILD 001 FINISHED");
    return 0;
}
