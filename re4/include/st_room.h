#ifndef ST_ROOM_H
#define ST_ROOM_H

#include "types.h"

// Shared by the stage room scripts (src/st1/, src/st2/, src/st3/, src/st4/). Nothing here emits code or data
// into .text/.rodata; the original room headers are unknown.

// Every original stage module carries a 0x34-byte COMMON block: uninitialised static data members
// that g++ 2.95 emits as `.comm` in every object, merged by the -r link and appended to .bss by
// snmakerel (tools/make_rel.py); their names are not in the binary. The generated skeleton calls the
// block `common_<mod>`, so the compiled rooms define the same symbol (REL_MODULE comes from
// configure.py) and the link keeps merging them into the one block whatever mix of split and
// compiled objects the module has.
#define ST_STR2(x) #x
#define ST_STR(x) ST_STR2(x)
asm(".comm common_" ST_STR(REL_MODULE) ",52,4");

// The rooms store into pG and their work with plain `pG->x = v` / `w->x = v`; ref_access.h keeps the
// few reference helpers that still change the code (VecSet in r202 / r208 / r219).
#include "ref_access.h"


#endif
