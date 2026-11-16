#include "rev_local_input.h"

void rev_local_input_init(RevLocalInput *local, uint32_t switch_button_mask)
{
    if (!local)
        return;

    rev_control_router_init(&local->router);
    local->switch_button_mask = switch_button_mask;
}

int rev_local_input_dispatch(RevLocalInput *local,
                             const RevPadInput *pad,
                             RevActorInputFn dispatch,
                             void *user_data,
                             uint8_t *active_actor,
                             uint8_t *switched)
{
    RevControlRoute route;

    if (active_actor)
        *active_actor = 0;
    if (switched)
        *switched = 0;

    if (!local || !pad || !dispatch)
        return 0;

    route = rev_control_router_update(&local->router,
                                     pad->buttons,
                                     local->switch_button_mask);

    dispatch(route.active_player, pad, user_data);

    if (active_actor)
        *active_actor = route.active_player;
    if (switched)
        *switched = route.changed;

    return 1;
}
