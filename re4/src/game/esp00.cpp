// game/esp00.cpp: effect id 0x00, the plain sprite. No per-effect work: standard motion
// (cEsp::CommonMove) plus texture animation, drawn by EspCommonTrans; released when the
// animation finishes.

#include "esp.h"

class cEsp00 : public cEsp {
public:
    virtual void move();
};

// EspCreateTbl[0x00] factory: allocates a cEsp00 from the esp pool (pDmyEsp when full).
cEsp* Esp00_Create()
{
    return new cEsp00;
}

// Per-frame update (EspMove): base motion/colour/life, then the texture animation; the effect is
// released when a non-looping animation reaches its last pattern.
void cEsp00::move()
{
    if (CommonMove()) {
        if (!AnmMove()) {
            PushEsp(this);
        }
    }
}
