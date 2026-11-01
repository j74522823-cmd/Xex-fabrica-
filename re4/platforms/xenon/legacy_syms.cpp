// Symbols the decompilation reached by their GCC 2.95 / SN linker names, or got from the link of the original game.
#include "types.h"
#include "global.h"
#include "event.h"
#include "snd.h"
#include "obj02.h"
#include "main_sub.h"

void Filter09Render();

// exception.cpp (the Gekko exception handler) is not built: xsdk has its own fault handling.
void ExceptionInit() {}

// Aliases made with asm("...") in game units (a calling convention / register-allocation trick for byte matching): the old
// GCC 2.95 mangled name of the function, forwarded to the real one.
extern "C" {
void FlgOnStatus__5EventUl(Event* e, u32 no) { e->FlgOnStatus(no); }
u32 SndCall__FUsUsP3VeciiP5cUnit(u16 blk, u16 no, Vec* pos, int id, int vol, cUnit* obj) { return SndCall(blk, no, pos, id, vol, obj); }
void Filter09Render__Fv(int) { Filter09Render(); }
void ScreenReSize__FUsUs(int w, int h) { ScreenReSize((u16) w, (u16) h); }
void SetCallBack__7cObjScrPFP4cObj_v(cObj* o, void (*func)(cObj*)) { ((cObjScr*) o)->SetCallBack(func); }

// GCC 2.95's operator new / delete.
void* __builtin_new(unsigned int size) { return ::operator new(size); }
void __builtin_delete(void* p) { ::operator delete(p); }
void* __builtin_vec_new(unsigned int size) { return ::operator new[](size); }
void __builtin_vec_delete(void* p) { ::operator delete[](p); }

// The linker script's labels on the static constructor / destructor lists (st1.cpp walks them when a stage REL loads). With
// the overlays linked into the XEX, xsdk's start-up runs the constructors once: the lists are empty.
void (*_ctors[1])(void) = {0};
void (*_dtors[1])(void) = {0};
}

// A room function that this REL's stage module does not contain was an unresolved relocation on the GameCube: calling it
// reached the module's _unresolved (HALT).
extern "C" void re4_unresolved(const char* name)
{
    OSReport("HALT: unresolved REL call %s\n", name);
    for (;;) {
    }
}
