#ifndef REV_LOCAL_INPUT_H
#define REV_LOCAL_INPUT_H

#include <stdint.h>
#include "rev_control_router.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Platform-neutral controller snapshot. The game-specific adapter must copy
 * the active local pad's buttons/axes into this structure once per frame.
 */
typedef struct RevPadInput {
    uint32_t buttons;
    int16_t left_x;
    int16_t left_y;
    int16_t right_x;
    int16_t right_y;
    uint8_t left_trigger;
    uint8_t right_trigger;
} RevPadInput;

typedef void (*RevActorInputFn)(uint8_t actor_index,
                                const RevPadInput *input,
                                void *user_data);

typedef struct RevLocalInput {
    RevControlRouter router;
    uint32_t switch_button_mask;
} RevLocalInput;

void rev_local_input_init(RevLocalInput *local, uint32_t switch_button_mask);

/*
 * Routes one local controller snapshot to exactly one logical actor.
 * Returns 1 when dispatched, 0 for invalid arguments.
 * The selected actor index is 0 (primary) or 1 (partner).
 */
int rev_local_input_dispatch(RevLocalInput *local,
                             const RevPadInput *pad,
                             RevActorInputFn dispatch,
                             void *user_data,
                             uint8_t *active_actor,
                             uint8_t *switched);

#ifdef __cplusplus
}
#endif

#endif
