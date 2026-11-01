// game/light03: light type 3, slowly turning directional light (D:/Bio4/Prog/light03.cpp): the
// normal is rotated by the work's angle vector (radians) every frame.
#include "light.h"
#include "math_sub.h"

// LightFuncTbl[3]: rotates l->normal by the work angles (re-seeding a degenerate normal to +z) and
// copies Col to DispCol.
// Directional light whose direction is rotated by the work angles every frame.
void Light03_Move(cLight* pLi)
{
    Vec* n = &pLi->normal;
    Vec* rot = (Vec*)pLi->work;
    Mtx m;

    if (PSVECMag(n) < 0.9f) {
        n->x = 0.0f;
        n->y = 0.0f;
        n->z = 1.0f;
    }
    RotMatrix(m, rot);
    PSMTXMultVec(m, n, n);
#line 48 "D:/Bio4/Prog/light03.cpp"
    VECNormalize(n, n);
    pLi->DispCol = pLi->Col;
}
