// game/at_sub2.cpp: the surface effect lookup for weapon hits. AtEffInfo (one per scenario
// attribute type, registered by the room) lists effect id pairs per weapon class; getWepEff
// picks the pair for a weapon id.

#include "atari.h"
#include "at_sub2.h"

// Effect (owner / est id) pair for a hit of weapon `wepId` on this surface: guns share effGun,
// 0x13 / 0x16 / 0x17 / 0xD (explosive, grenade types, mine) have their own. 0 with an error for
// weapons without a surface effect.
int AtEffInfo::getWepEff(int wepNo, u32* type, u32* id)
{
    int ret = 1;

    switch (wepNo) {
    case 1:  // handguns
    case 2:
    case 3:
    case 4:
        *type = effGun[0];
        *id = effGun[1];
        break;
    case 5:  // shotguns
    case 6:
    case 7:
    case 8:
        *type = effGun[0];
        *id = effGun[1];
        break;
    case 9:  // rifles
    case 10:
    case 11:
    case 12:
        *type = effGun[0];
        *id = effGun[1];
        break;
    case 0x0F:
    case 0x11:
    case 0x21:
        *type = effGun[0];
        *id = effGun[1];
        break;
    case 0x13:
        *type = eff13[0];
        *id = eff13[1];
        break;
    case 0x16:
        *type = eff16[0];
        *id = eff16[1];
        break;
    case 0x17:
        *type = eff17[0];
        *id = eff17[1];
        break;
    case 0x0D:
        *type = eff0D[0];
        *id = eff0D[1];
        break;
    default:
        ret = 0;
        pLog->err(0, 0, "getWepEff() INVALID ARG %d %d %d", wepNo, *type, *id);
        break;
    }
    return ret;
}
