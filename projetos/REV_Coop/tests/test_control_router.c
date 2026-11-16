#include <assert.h>
#include <stdint.h>
#include "rev_control_router.h"

int main(void)
{
    RevControlRouter router;
    RevControlRoute route;
    const uint32_t toggle = 0x00000001u;

    rev_control_router_init(&router);

    route = rev_control_router_update(&router, 0, toggle);
    assert(route.active_player == 0 && route.changed == 0);

    /* First press switches to partner. */
    route = rev_control_router_update(&router, toggle, toggle);
    assert(route.active_player == 1 && route.changed == 1);

    /* Holding the button must not switch repeatedly. */
    route = rev_control_router_update(&router, toggle, toggle);
    assert(route.active_player == 1 && route.changed == 0);

    /* Release, then press again to return to primary. */
    route = rev_control_router_update(&router, 0, toggle);
    assert(route.active_player == 1 && route.changed == 0);
    route = rev_control_router_update(&router, toggle, toggle);
    assert(route.active_player == 0 && route.changed == 1);

    /* Null input is handled safely. */
    route = rev_control_router_update(0, toggle, toggle);
    assert(route.active_player == 0 && route.changed == 0);

    return 0;
}
