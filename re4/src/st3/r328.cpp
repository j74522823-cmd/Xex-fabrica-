#include "types.h"
#include "main_mem.h"
#include "st_room.h"
#include "flag_rsf.h"

// Room 3-28 (D:/Bio4/Prog/r328.cpp): a room with no script — R328Init only allocates the (empty)
// work and R328Main does nothing.

struct R328Work {
    u8 dummy;
};

static R328Work* r328_work;

// Room init: allocates the (empty) work only; the room has no script.
void R328Init()
{
#line 26 "D:/Bio4/Prog/r328.cpp"
    r328_work = (R328Work*) MEM_CALLOC(sizeof(R328Work), 1, 0xd);
}

// Per-frame room main: nothing.
void R328Main()
{
}
