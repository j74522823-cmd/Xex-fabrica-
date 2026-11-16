#include "rev_control_router.h"

void rev_control_router_init(RevControlRouter *router)
{
    if (!router)
        return;

    router->previous_buttons = 0;
    router->active_player = 0;
}

RevControlRoute rev_control_router_update(
    RevControlRouter *router,
    uint32_t buttons,
    uint32_t toggle_mask
)
{
    RevControlRoute result = {0, 0};

    if (!router)
        return result;

    const uint32_t pressed_now = buttons & toggle_mask;
    const uint32_t pressed_before = router->previous_buttons & toggle_mask;
    const int pressed_edge = (pressed_now != 0) && (pressed_before == 0);

    if (pressed_edge)
    {
        router->active_player = (uint8_t)(router->active_player ^ 1u);
        result.changed = 1;
    }

    router->previous_buttons = buttons;
    result.active_player = router->active_player;
    return result;
}
