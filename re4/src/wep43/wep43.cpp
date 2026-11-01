// wep43 module: Wesker's handgun (the Punisher class object wep/objRuger.cpp, object id 0x21).
// Creates the weapon object, loads the muzzle effects and the player's weapon motions, and registers
// the handgun player routines (wep/pl_handgun.cpp).

#include "wep_mod.h"
#include "light.h"
#include "esp.h"

void PlHandgunMove(cPlayer* pl);   // wep/pl_handgun.cpp
void ObjRuger_init(cObj* obj);     // wep/objRuger.cpp

// WeaponInitFunc (cPlayer::weaponInit with the player): creates the cObjRuger (ObjMgr id 0x21)
// as Wep->m_pWep, inits it on the player, installs its motions, loads the muzzle-flash effects
// (archive 0x4 as group 0x36) and points the debug preview PlWepMot at 0x26..0x28.
void Wep43_init(cModel* m)
{
    cPlayer* pl = (cPlayer*) m;
    cObjWep* obj;

    obj = (cObjWep*) ObjMgr.createBack(cObjMgr::ID_WEP_RUGER);
    if (obj == 0) {
        pLog->err(0, 0, "Wep43_init() cObjWep CREATE FAILED");
    } else {
        pl->Wep->m_pWep = obj;
        obj->init(pl);
        obj->setMotion(pl);
        EspDataLoad((u32) WEP_ARC_PTR(0x4), EFF_WEP02, 1);
        PlWepMot[0] = WEP_ARC_PTR(0x26);
        PlWepMot[1] = WEP_ARC_PTR(0x27);
        PlWepMot[2] = WEP_ARC_PTR(0x28);
    }
}

// REL entry: registers the weapon init / move routines and the object constructor slot.
extern "C" void _prolog()
{
    WeaponInitFunc = Wep43_init;
    WeaponMoveFunc = PlHandgunMove;
    ObjInitFunc[0x21] = ObjRuger_init;
    OSReport("Wep43 WESKER - HANDGUN prolog Ok\n");
}

// REL exit: frees the object constructor slot.
extern "C" void _epilog()
{
    ObjInitFunc[0x21] = 0;
}

// Target of every unresolved cross-module branch (snmakerel patches them to `bl _unresolved`).
extern "C" void _unresolved()
{
}
