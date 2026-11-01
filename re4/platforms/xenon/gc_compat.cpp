#include "gc_compat.h"
#include "vec.h"

extern "C" {
// 32-byte aligned like the real locked cache lines.
u8 g_LockedCache[0x4000] __attribute__((aligned(32)));
}

// Projective transform of a point by a 4x4 matrix with the divide by w (Gekko had this as paired singles).
extern "C" void RE4_MTX44MultVec(const Mtx44 m, const Vec* src, Vec* dst)
{
    float x = src->x, y = src->y, z = src->z;
    float w = m[3][0] * x + m[3][1] * y + m[3][2] * z + m[3][3];
    float inv = 1.0f / w;
    dst->x = (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3]) * inv;
    dst->y = (m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3]) * inv;
    dst->z = (m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3]) * inv;
}

// ---- charPipeline utilities (the SDK's list and string helpers; not in Aurora, not in the decomp's src/lib) --------------
#include "charPipeline/structures.h"
#include <string.h>

extern "C" {
void DSInitList(DSListPtr list, Ptr obj, DSLinkPtr link)
{
    list->Head = list->Tail = NULL;
    list->Offset = (u32) link - (u32) obj;   // where the link sits inside an object
}

static inline DSLinkPtr dsLink(DSListPtr list, Ptr obj) { return (DSLinkPtr) ((u32) obj + list->Offset); }

// Inserts `obj` before `cursor`; a NULL cursor appends at the tail.
void DSInsertListObject(DSListPtr list, Ptr cursor, Ptr obj)
{
    DSLinkPtr l = dsLink(list, obj);
    if (cursor == NULL) {
        l->Next = NULL;
        l->Prev = list->Tail;
        if (list->Tail) {
            dsLink(list, list->Tail)->Next = obj;
        } else {
            list->Head = obj;
        }
        list->Tail = obj;
    } else {
        DSLinkPtr c = dsLink(list, cursor);
        l->Next = cursor;
        l->Prev = c->Prev;
        if (c->Prev) {
            dsLink(list, c->Prev)->Next = obj;
        } else {
            list->Head = obj;
        }
        c->Prev = obj;
    }
}

void DSRemoveListObject(DSListPtr list, Ptr obj)
{
    DSLinkPtr l = dsLink(list, obj);
    if (l->Prev) {
        dsLink(list, l->Prev)->Next = l->Next;
    } else {
        list->Head = l->Next;
    }
    if (l->Next) {
        dsLink(list, l->Next)->Prev = l->Prev;
    } else {
        list->Tail = l->Prev;
    }
    l->Next = l->Prev = NULL;
}

void DSAttachList(DSListPtr base, DSListPtr attach)
{
    if (attach->Head == NULL) {
        return;
    }
    if (base->Tail) {
        dsLink(base, base->Tail)->Next = attach->Head;
        dsLink(attach, attach->Head)->Prev = base->Tail;
    } else {
        base->Head = attach->Head;
    }
    base->Tail = attach->Tail;
    attach->Head = attach->Tail = NULL;
}

void* DSNextListObj(DSListPtr list, Ptr obj)
{
    return obj ? dsLink(list, obj)->Next : list->Head;
}

u8 Strcat(char* s1, char* s2, char* dst)
{
    size_t n = strlen(s1);
    memmove(dst, s1, n);
    strcpy(dst + n, s2);
    return 1;
}
void Strcpy(char* dst, char* src) { strcpy(dst, src); }
s8 Strcmp(char* a, char* b)
{
    int r = strcmp(a, b);
    return r < 0 ? -1 : (r > 0 ? 1 : 0);
}
u32 Strlen(char* s) { return (u32) strlen(s); }
}
