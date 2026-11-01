// wep02 module: the Red9 (cObjMauser, object id 0x27) and Punisher (cObjRuger, 0x21) handguns.
// Creates the weapon object of the equipped type, loads the muzzle effects and the player's
// weapon motions, and registers the handgun player routines (wep/pl_handgun.cpp).

#include "wep_mod.h"
#include "light.h"
#include "esp.h"

void PlHandgunMove(cPlayer* pl);   // wep/pl_handgun.cpp
void ObjMauser_init(cObj* obj);    // objMauser.cpp
void ObjRuger_init(cObj* obj);     // objRuger.cpp

// WeaponInitFunc of the module (cPlayer::weaponInit with the player): creates the weapon object of
// the equipped handgun (weapon_no 2 Punisher -> cObjRuger id 0x21, 3 Red9 -> cObjMauser 0x27) as
// Wep->m_pWep, inits it on the player, installs its motions, loads the muzzle-flash effects
// (archive 0x4 as group 0x36) and points the debug preview PlWepMot at the aim motions 0x26..0x28.
void Wep02_init(cModel* m)
{
    cPlayer* pl = (cPlayer*) m;
    cObjWep* obj;
    int id;

    switch (pG->weapon_no) {
    case 2:
    default:
        id = 0x21;
        break;
    case 3:
        id = 0x27;
        break;
    }
    obj = (cObjWep*) ObjMgr.createBack(id);
    if (obj == 0) {
        pLog->err(0, 0, "Wep02_init() cObjWep CREATE FAILED");
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

// REL entry: registers the weapon init / move routines and both object constructor slots.
extern "C" void _prolog()
{
    WeaponInitFunc = Wep02_init;
    WeaponMoveFunc = PlHandgunMove;
    ObjInitFunc[0x21] = ObjRuger_init;
    ObjInitFunc[0x27] = ObjMauser_init;
    OSReport("Wep02 HANDGUN prolog Ok\n");
}

// REL exit: frees the object constructor slots.
extern "C" void _epilog()
{
    ObjInitFunc[0x21] = 0;
    ObjInitFunc[0x27] = 0;
}

// Target of every unresolved cross-module branch (snmakerel patches them to `bl _unresolved`).
extern "C" void _unresolved()
{
}
