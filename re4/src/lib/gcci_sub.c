/* CRI GCCI settings (gcci_sub.c): the DVD read mode (0 asynchronous DVDReadAsyncPrio, else blocking
 * DVDReadPrio) and the root directory prepended to every CVFS path (empty in this game). */
#include "cri_xpt.h"

#pragma explicit_zero_data on

Sint32 gcg_ci_rdmode = 0;
Sint32 gcg_ci_sub_work = 0;
Char8 gcg_ci_root_dir[256];

// Sets gcg_ci_rdmode; ADXGC_SetupDvdFs passes the game's choice (0 = asynchronous).
void gcCiSetRdMode(void *obj, Sint32 a, Sint32 b, Sint32 mode)
{
	gcg_ci_rdmode = mode;
}
