// game/light10: light type 0x10, muzzle flash / explosion fade-out (D:/Bio4/Prog/light10.cpp).
#include "light.h"

struct Light10Work {
    u8 wait;  // 0x00 frames before the fade starts
};

// LightFuncTbl[0x10]: waits `wait` frames, then multiplies Intensity by 0.3 each frame and deletes
// the light below 0.1.
// Fade-out light: waits, then decays power by 30% a frame and dies below 0.1.
void Light10_Move(cLight* pLight)
{
    Light10Work* w = (Light10Work*)pLight->work;

    if (w->wait != 0) {
        w->wait--;
        return;
    }
    pLight->Intensity *= 0.3f;
    if (pLight->Intensity < 0.1f) {
        pLight->Intensity = 0.0f;
        delete pLight;
    }
}
