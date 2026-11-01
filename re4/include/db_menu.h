#ifndef DB_MENU_H
#define DB_MENU_H

#include "types.h"

// Debug menu (game/db_menu.cpp). The selected entry is what the tool modules and se_at.cpp test.
// db_menu.cpp does not include this header: DebugMenuSelected is uninitialised and a declaration ahead
// of its definition would reorder the unit's .sbss.

extern int DebugMenuSelected;

#endif
