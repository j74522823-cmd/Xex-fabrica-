#ifndef T_UTIL_H
#define T_UTIL_H

#include "types.h"
#include "global.h"
#include "joy.h"
#include "eprintf.h"

// Debug tool helpers (game/t_util.cpp).

// One menu line for ToolMenuDisp_cur (0xC bytes).
struct TOOL_MENU {
    u8 Be_flg;          // 0x00  0 = greyed out (color 0x14) and not selectable
    const char* pName;   // 0x04
    void (*pFunc)();     // 0x08  called when selected (may be NULL)
};

// ToolMenuDisp_cur flag bits
#define TOOL_MENU_B_LAST   1  // B button jumps to the last entry
#define TOOL_MENU_START_LAST 2  // cursor starts on the last entry for a new menu

void TutilInitDefault();
void TutilQuitDefault();
// Draws `menu` (size in bytes) at x,y and moves the cursor with `joy`. Returns the selected
// entry when A is pressed on an enabled line, else -1. `cursor` may be NULL.
int ToolMenuDisp_cur(int x, int y, int flg, s8* pCur, TOOL_MENU* pMenu, int MenuSize, JOY* pJoy1);
// tools/t_util.cpp only (dead-stripped from the DOL): screen position of a world point.
int TutilGetScreenPos(Vec* mv, f32* sv, int mode);
void TutilMoveCursor(Vec* pos, f32 anamv, f32 keymv);
// t_event/t_sce: ToolMenuDisp_cur without a cursor variable
int ToolMenuDisp(int x, int y, int flg, TOOL_MENU* pMenu, int MenuSize, JOY* pJoy1);
// Tools only: XZ position under a screen point (projection search around `center`, side `step`).
int TutilGet3DPosXZ(Vec* sv, Vec* bmv, f32 width, Vec* mv);
int TutilGet3DPosXZ_Mov(Vec* sv, Vec* bmv, Vec* mv);
int TutilGet3DPosXZ_All(Vec* sv, Vec* bmv, Vec* mv);

// Prints `n` menu strings one row (14 px) apart; inlined (the giv inits land after the PRE'd pointer
// high parts in the preheader) (t_cons, t_scroll; t_tplview has its own `*tbl++` form).
static inline void dispList(int x, int y, char** tbl, int n)
{
    int i;

    for (i = 0; i < n; i++) {
        eprintf(x, y + i * 14, 0, 0, tbl[i]);
    }
}

#endif
