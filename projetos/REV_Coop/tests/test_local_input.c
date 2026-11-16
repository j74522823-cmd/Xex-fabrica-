#include <assert.h>
#include <stdint.h>
#include "rev_local_input.h"

typedef struct DispatchLog {
    unsigned calls;
    uint8_t actor;
    RevPadInput last;
} DispatchLog;

static void record_dispatch(uint8_t actor, const RevPadInput *input,
                            void *user_data)
{
    DispatchLog *log = (DispatchLog *)user_data;
    ++log->calls;
    log->actor = actor;
    log->last = *input;
}

int main(void)
{
    RevLocalInput local;
    DispatchLog log = {0};
    RevPadInput pad = {0};
    uint8_t actor = 99;
    uint8_t switched = 99;

    rev_local_input_init(&local, 0x00000001u);

    /* One local pad initially controls the primary actor. */
    pad.buttons = 0;
    pad.left_x = 1234;
    assert(rev_local_input_dispatch(&local, &pad, record_dispatch,
                                    &log, &actor, &switched) == 1);
    assert(log.calls == 1 && log.actor == 0);
    assert(log.last.left_x == 1234);
    assert(actor == 0 && switched == 0);

    /* A fresh press routes the same pad to the partner. */
    pad.buttons = 0x00000001u;
    pad.left_y = -2345;
    assert(rev_local_input_dispatch(&local, &pad, record_dispatch,
                                    &log, &actor, &switched) == 1);
    assert(log.calls == 2 && log.actor == 1);
    assert(log.last.left_y == -2345);
    assert(actor == 1 && switched == 1);

    /* Holding switch does not toggle back. */
    assert(rev_local_input_dispatch(&local, &pad, record_dispatch,
                                    &log, &actor, &switched) == 1);
    assert(log.calls == 3 && actor == 1 && switched == 0);

    /* Release and press again returns control to primary. */
    pad.buttons = 0;
    assert(rev_local_input_dispatch(&local, &pad, record_dispatch,
                                    &log, &actor, &switched) == 1);
    pad.buttons = 1;
    assert(rev_local_input_dispatch(&local, &pad, record_dispatch,
                                    &log, &actor, &switched) == 1);
    assert(log.calls == 5 && actor == 0 && switched == 1);

    /* Invalid inputs are rejected without calling the game adapter. */
    assert(rev_local_input_dispatch(&local, 0, record_dispatch,
                                    &log, &actor, &switched) == 0);
    assert(rev_local_input_dispatch(&local, &pad, 0,
                                    &log, &actor, &switched) == 0);
    assert(log.calls == 5);

    return 0;
}
