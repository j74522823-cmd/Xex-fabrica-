// wep01 module: the FN57 (Blacktail) handgun (class object objFn57.cpp, object id 0x32).
// Creates the weapon object, loads the muzzle effects and the player's weapon motions, and registers
// the handgun player routines (wep/pl_handgun.cpp).

#include "wep_mod.h"
#include "light.h"
#include "esp.h"

void PlHandgunMove(cPlayer* pl);   // wep/pl_handgun.cpp
void ObjFn57_init(cObj* obj);      // objFn57.cpp

// WeaponInitFunc of the module (cPlayer::weaponInit with the player): creates the cObjFn57 (ObjMgr
// id 0x32) as the player's weapon (Wep->m_pWep), inits it on the player, installs the handgun
// motions, loads the muzzle-flash effect data (archive 0x4 as effect group 0x35) and points the
// debug weapon-motion preview PlWepMot at the aim motions 0x26..0x28.
void Wep01_init(cModel* m)
{
    cPlayer* pl = (cPlayer*) m;
    cObjWep* obj;

    obj = (cObjWep*) ObjMgr.createBack(cObjMgr::ID_WEP_FN57);
    if (obj == 0) {
        pLog->err(0, 0, "Wep01_init() cObjFn57 CREATE FAILED");
    } else {
        pl->Wep->m_pWep = obj;
        obj->init(pl);
        obj->setMotion(pl);
        EspDataLoad((u32) WEP_ARC_PTR(0x4), EFF_WEP01, 1);
        PlWepMot[0] = WEP_ARC_PTR(0x26);
        PlWepMot[1] = WEP_ARC_PTR(0x27);
        PlWepMot[2] = WEP_ARC_PTR(0x28);
    }
}

// REL entry: registers the weapon init / move routines and the object constructor slot.
extern "C" void _prolog()
{
    WeaponInitFunc = Wep01_init;
    WeaponMoveFunc = PlHandgunMove;
    ObjInitFunc[0x32] = ObjFn57_init;
    OSReport("Wep01 FN57 prolog Ok\n");
}

// REL exit: frees the object constructor slot.
extern "C" void _epilog()
{
    ObjInitFunc[0x32] = 0;
}

// Target of every unresolved cross-module branch (snmakerel patches them to `bl _unresolved`).
extern "C" void _unresolved()
{
}
