// game/TmpBuf.cpp: the shared 0x38000 byte draw scratch buffer (frame buffer copies of the
// screen effects, texture render targets). g_Type records which user filled it last so effects
// can tell whether the copy is still theirs.

#include "main_mem.h"

// Shared scratch buffer for the draw pipeline.
void* g_pDrawTmpBuffer;
int g_Type;

void SetDrawTmpBufType(int type);

// Allocates the scratch buffer (room start) and marks it unused (type 0).
#line 43 "D:/Bio4/Prog/TmpBuf.cpp"
void AllocDrawTmpBuf()
{
    g_pDrawTmpBuffer = MEM_ALLOC(0x38000, 1, 13);
    SetDrawTmpBufType(0);
}

// Claims the buffer for user `type` and returns it.
void* GetDrawTmpBufAddr(int type)
{
    SetDrawTmpBufType(type);
    return g_pDrawTmpBuffer;
}

// Records the current user.
void SetDrawTmpBufType(int type)
{
    g_Type = type;
}

// The current user of the buffer.
int GetDrawTmpBufType()
{
    return g_Type;
}
