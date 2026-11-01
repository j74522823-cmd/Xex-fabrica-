#include "types.h"
#include "global.h"
#include "db_log.h"
#include "scheduler.h"
#include "block.h"
#include "camera.h"
#include "cam_ctrl.h"
#include "player.h"
#include "light.h"
#include "t_util.h"
#include "db_light.h"

// Light tool entry of the t_light REL (the light editor itself is tools/db_light.cpp: cLightTool
// edits the room's .lit cuts, lights, ambient, fog, focus ...). ToolLight only creates the editor,
// runs it every frame and cleans up.

// LIGHT TOOL entry (debug menu 8): suspends the game, creates the db_light cLightTool and runs its
// move() every frame (result 2 = player mode: the player, camera control and camera also run);
// Debug_flg bits 29/28/4 mark the tool active; ends the task when the editor quits.
void ToolLight()
{
    cLightTool* tool;

    TaskSuspend(0);
    TaskSleep(1);
    TutilInitDefault();
    tool = new cLightTool;
    Block.dispAllBlock(1);
    if ((u32) tool >= 0x80000000 && (u32) tool <= 0x82FFFFFF) {
        int ret;

        DbgFlagOn(pG, DBG_BACK_CLIP);
        DbgFlagOn(pG, DBG_DBG_CAM);
        DbgFlagOn(pG, DBG_LIGHT_TOOL);
        while ((ret = tool->move()) != 0) {
            if (ret == 2) {
                pPL->move();
                CamCtrl.Check();
                CameraMove();
            }
            TaskSleep(1);
        }
        delete tool;
        Block.dispAllBlock(0);
        DbgFlagOff(pG, DBG_LIGHT_TOOL);
        DbgFlagOff(pG, DBG_DBG_CAM);
        DbgFlagOff(pG, DBG_BACK_CLIP);
    } else {
        pLog->err(0, 0, "BOOT LIGHT TOOL WAS FAILED. MEMORY LACK");
    }
    DbgFlagOff(pG, DBG_TEST_MODE);
    TutilQuitDefault();
    TaskSignal(0);
    TaskExit();
}
