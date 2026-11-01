#ifndef ST_MGR_EVENT_H
#define ST_MGR_EVENT_H

#include "types.h"
#include "cManager.h"


template <class T>
void cManager<T>::beginEvent(int mode)
{
    u32 i;

    for (i = 0; i < nArray; i++) {
        T* p = (T*) ((u8*) pArray + size * i);
        if (p->isAlive()) {
            p->beginEvent(mode);
        }
    }
}

template <class T>
void cManager<T>::endEvent(int mode)
{
    u32 i;

    for (i = 0; i < nArray; i++) {
        T* p = (T*) ((u8*) pArray + size * i);
        if (p->isAlive()) {
            p->endEvent(mode);
        }
    }
}

#endif
