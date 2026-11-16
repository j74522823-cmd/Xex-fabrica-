#ifndef REV_CONTROL_ROUTER_H
#define REV_CONTROL_ROUTER_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Single-controller control routing prototype.
 *
 * This module does NOT create a game actor or patch Revelations. It only
 * decides which logical player should receive the current controller input.
 * The game-specific integration must feed the returned player index into
 * the real player/partner input update path.
 */

typedef struct RevControlRouter {
    uint32_t previous_buttons;
    uint8_t active_player; /* 0 = primary, 1 = partner */
} RevControlRouter;

typedef struct RevControlRoute {
    uint8_t active_player;
    uint8_t changed;
} RevControlRoute;

void rev_control_router_init(RevControlRouter *router);

/*
 * toggle_mask is the bit (or combination of bits) chosen for switching.
 * A switch occurs only on the rising edge, not while the button is held.
 */
RevControlRoute rev_control_router_update(
    RevControlRouter *router,
    uint32_t buttons,
    uint32_t toggle_mask
);

#ifdef __cplusplus
}
#endif

#endif
