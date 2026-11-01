#include "types.h"
#include "main_mem.h"
#include "st_room.h"
#include "flag_rsf.h"

// Room 1-0d (D:/Bio4/Prog/r10d.cpp): a room with no script — R10dInit only allocates the (empty)
// work and R10dMain does nothing; everything in it is data-driven (ESL, SceAt areas, the SMD).

struct R10dWork {
    u8 pad[1];
};

static R10dWork* r10d_work;

// Room init (St1_data_tbl entry 0x0D): allocates the (empty) work only; the room has no script.
void R10dInit()
{
#line 26 "D:/Bio4/Prog/r10d.cpp"
    r10d_work = (R10dWork*) MEM_CALLOC(1, 1, 0xd);
}

// Per-frame room main: nothing.
void R10dMain()
{
}
