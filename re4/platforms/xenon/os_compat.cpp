// Xbox 360 side of the Dolphin OS layer that Aurora only declares (threads, semaphores, interrupts, OSReport, ...).
//
// Threads: the game's task scheduler (src/game/scheduler.cpp) runs each task as an OS thread, and hands the CPU over with
// OSResumeThread / OSSuspendThread / OSSleepThread / OSWakeupThread, relying on the Dolphin rule that the highest-priority
// ready thread runs. This is that rule on top of pthreads: exactly ONE thread runs at a time (the "baton"), and it changes
// hands only inside these calls, so the game never needs real locks. Lower number = higher priority, as on Dolphin.
#include <dolphin/os.h>
#include <dolphin/vi.h>
#include <dolphin/ar.h>
#include <dolphin/ai.h>
#include <dolphin/os/OSSemaphore.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <time.h>
#include <setjmp.h>
#include <xsdk/log.h>
extern "C" void re4_diag_write(const char* message);

namespace {

struct Ext {
    OSThread* t;
    pthread_t pt;
    pthread_cond_t cv;
    jmp_buf jb;   // where a finished or cancelled thread unwinds to (xsdk has no pthread_exit)
    bool started;
    bool die;
    void* (*func)(void*);
    void* param;
    unsigned seq;   // FIFO order among equal priorities
};

constexpr int MAX_THREADS = 48;
pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
Ext* g_ext[MAX_THREADS];
OSThread g_mainThread;
OSThread* g_current;
unsigned g_seq;
bool g_init;
int g_intLevel;   // OSDisableInterrupts nesting (nothing preempts between OS calls, so it is bookkeeping only)

Ext* ext_of(OSThread* t) { return (Ext*) t->specific[1]; }

bool runnable(OSThread* t)
{
    return t->suspend <= 0 && (t->state == OS_THREAD_STATE_READY || t->state == OS_THREAD_STATE_RUNNING);
}

void init_locked()
{
    if (g_init) {
        return;
    }
    g_init = true;
    memset(&g_mainThread, 0, sizeof(g_mainThread));
    Ext* e = (Ext*) calloc(1, sizeof(Ext));
    e->t = &g_mainThread;
    e->pt = pthread_self();
    pthread_cond_init(&e->cv, NULL);
    e->started = true;
    e->seq = g_seq++;
    g_mainThread.state = OS_THREAD_STATE_RUNNING;
    g_mainThread.priority = g_mainThread.base = 16;
    g_mainThread.specific[1] = e;
    g_ext[0] = e;
    g_current = &g_mainThread;
}

Ext* pick_locked()
{
    Ext* best = NULL;
    for (int i = 0; i < MAX_THREADS; i++) {
        Ext* e = g_ext[i];
        if (!e || !runnable(e->t)) {
            continue;
        }
        if (!best || e->t->priority < best->t->priority ||
            (e->t->priority == best->t->priority && e->t == g_current) ||
            (e->t->priority == best->t->priority && best->t != g_current && e->seq < best->seq)) {
            best = e;
        }
    }
    return best;
}

// The caller holds g_lock. Gives the baton to the best runnable thread and, unless the caller is finished, waits until it is
// handed back.
void reschedule_locked(OSThread* self)
{
    Ext* me = ext_of(self);
    Ext* next = pick_locked();
    if (!next) {
        fprintf(stderr, "OS: no runnable thread (deadlock)\n");
        abort();
    }
    if (next->t == self) {
        self->state = OS_THREAD_STATE_RUNNING;
        return;
    }
    if (g_current->state == OS_THREAD_STATE_RUNNING) {
        g_current->state = OS_THREAD_STATE_READY;
    }
    g_current = next->t;
    next->t->state = OS_THREAD_STATE_RUNNING;
    pthread_cond_signal(&next->cv);
    if (self->state == OS_THREAD_STATE_MORIBUND) {
        return;   // never runs again
    }
    while (g_current != self) {
        pthread_cond_wait(&me->cv, &g_lock);
        if (me->die) {
            pthread_mutex_unlock(&g_lock);
            longjmp(me->jb, 1);
        }
    }
    self->state = OS_THREAD_STATE_RUNNING;
}

void queue_push(OSThreadQueue* q, OSThread* t)
{
    t->link.next = NULL;
    t->link.prev = q->tail;
    if (q->tail) {
        q->tail->link.next = t;
    } else {
        q->head = t;
    }
    q->tail = t;
    t->queue = q;
}

void queue_remove(OSThreadQueue* q, OSThread* t)
{
    if (t->link.prev) {
        t->link.prev->link.next = t->link.next;
    } else {
        q->head = t->link.next;
    }
    if (t->link.next) {
        t->link.next->link.prev = t->link.prev;
    } else {
        q->tail = t->link.prev;
    }
    t->queue = NULL;
}

void* thread_entry(void* arg)
{
    Ext* me = (Ext*) arg;
    if (setjmp(me->jb) != 0) {
        return NULL;   // OSExitThread / OSCancelThread unwound here
    }
    pthread_mutex_lock(&g_lock);
    while (g_current != me->t) {
        pthread_cond_wait(&me->cv, &g_lock);
        if (me->die) {
            pthread_mutex_unlock(&g_lock);
            return NULL;
        }
    }
    me->t->state = OS_THREAD_STATE_RUNNING;
    pthread_mutex_unlock(&g_lock);
    void* ret = me->func(me->param);
    OSExitThread(ret);
    return NULL;
}

}  // namespace

extern "C" {

// ---- threads -------------------------------------------------------------------------------------------------------
void OSInitThreadQueue(OSThreadQueue* queue)
{
    queue->head = queue->tail = NULL;
}

OSThread* OSGetCurrentThread(void)
{
    pthread_mutex_lock(&g_lock);
    init_locked();
    OSThread* t = g_current;
    pthread_mutex_unlock(&g_lock);
    return t;
}

BOOL OSCreateThread(OSThread* thread, void* (*func)(void*), void* param, void* stack, u32 stackSize, OSPriority priority,
                    u16 attr)
{
    pthread_mutex_lock(&g_lock);
    init_locked();
    int slot = -1;
    for (int i = 0; i < MAX_THREADS; i++) {
        if (!g_ext[i]) {
            slot = i;
            break;
        }
    }
    if (slot < 0) {
        pthread_mutex_unlock(&g_lock);
        return FALSE;
    }
    Ext* e = (Ext*) calloc(1, sizeof(Ext));
    e->t = thread;
    e->func = func;
    e->param = param;
    e->seq = g_seq++;
    pthread_cond_init(&e->cv, NULL);
    thread->state = OS_THREAD_STATE_READY;
    thread->attr = attr;
    thread->suspend = 1;   // starts suspended; OSResumeThread starts it
    thread->priority = thread->base = priority;
    thread->val = NULL;
    thread->queue = NULL;
    thread->stackBase = (u8*) stack;
    thread->stackEnd = (u8*) stack - stackSize;
    thread->specific[1] = e;
    g_ext[slot] = e;
    pthread_attr_t at;
    pthread_attr_init(&at);
    pthread_attr_setstacksize(&at, 512 * 1024);   // the GameCube stacks (0x1800..0x3000) are far too small for newlib
    int rc = pthread_create(&e->pt, &at, thread_entry, e);
    pthread_attr_destroy(&at);
    if (rc != 0) {
        g_ext[slot] = NULL;
        free(e);
        pthread_mutex_unlock(&g_lock);
        return FALSE;
    }
    e->started = true;
    pthread_mutex_unlock(&g_lock);
    return TRUE;
}

s32 OSResumeThread(OSThread* thread)
{
    pthread_mutex_lock(&g_lock);
    init_locked();
    s32 old = thread->suspend;
    if (thread->suspend > 0) {
        thread->suspend--;
    }
    if (thread->suspend <= 0) {
        reschedule_locked(g_current);   // the resumed thread may outrank the caller
    }
    pthread_mutex_unlock(&g_lock);
    return old;
}

s32 OSSuspendThread(OSThread* thread)
{
    pthread_mutex_lock(&g_lock);
    init_locked();
    s32 old = thread->suspend;
    thread->suspend++;
    if (thread == g_current) {
        reschedule_locked(g_current);
    }
    pthread_mutex_unlock(&g_lock);
    return old;
}

void OSSleepThread(OSThreadQueue* queue)
{
    pthread_mutex_lock(&g_lock);
    init_locked();
    OSThread* self = g_current;
    self->state = OS_THREAD_STATE_WAITING;
    queue_push(queue, self);
    reschedule_locked(self);
    pthread_mutex_unlock(&g_lock);
}

void OSWakeupThread(OSThreadQueue* queue)
{
    pthread_mutex_lock(&g_lock);
    init_locked();
    while (queue->head) {
        OSThread* t = queue->head;
        queue_remove(queue, t);
        t->state = OS_THREAD_STATE_READY;
    }
    reschedule_locked(g_current);
    pthread_mutex_unlock(&g_lock);
}

void OSExitThread(void* val)
{
    pthread_mutex_lock(&g_lock);
    init_locked();
    OSThread* self = g_current;
    self->val = val;
    self->state = OS_THREAD_STATE_MORIBUND;
    Ext* e = ext_of(self);
    for (int i = 0; i < MAX_THREADS; i++) {
        if (g_ext[i] == e) {
            g_ext[i] = NULL;
        }
    }
    reschedule_locked(self);
    pthread_mutex_unlock(&g_lock);
    if (self != &g_mainThread) {
        longjmp(e->jb, 1);
    }
}

void OSCancelThread(OSThread* thread)
{
    pthread_mutex_lock(&g_lock);
    init_locked();
    if (thread == g_current) {
        pthread_mutex_unlock(&g_lock);
        OSExitThread(NULL);
        return;
    }
    if (thread->queue) {
        queue_remove(thread->queue, thread);
    }
    thread->state = OS_THREAD_STATE_MORIBUND;
    Ext* e = ext_of(thread);
    for (int i = 0; i < MAX_THREADS; i++) {
        if (g_ext[i] == e) {
            g_ext[i] = NULL;
        }
    }
    e->die = true;
    pthread_cond_signal(&e->cv);
    pthread_mutex_unlock(&g_lock);
}

// ---- semaphores ----------------------------------------------------------------------------------------------------
void OSInitSemaphore(OSSemaphore* sem, s32 count)
{
    sem->count = count;
    OSInitThreadQueue(&sem->queue);
}

s32 OSWaitSemaphore(OSSemaphore* sem)
{
    s32 old;
    while ((old = sem->count) <= 0) {
        OSSleepThread(&sem->queue);
    }
    sem->count--;
    return old;
}

s32 OSSignalSemaphore(OSSemaphore* sem)
{
    s32 old = sem->count;
    sem->count++;
    OSWakeupThread(&sem->queue);
    return old;
}

// ---- interrupts: nothing preempts between OS calls ----------------------------------------------------------------
BOOL OSDisableInterrupts(void)
{
    BOOL was = (g_intLevel == 0);
    g_intLevel++;
    return was;
}

BOOL OSEnableInterrupts(void)
{
    BOOL was = (g_intLevel == 0);
    g_intLevel = 0;
    return was;
}

BOOL OSRestoreInterrupts(BOOL level)
{
    BOOL was = (g_intLevel == 0);
    if (level) {
        g_intLevel = 0;
    } else if (g_intLevel == 0) {
        g_intLevel = 1;
    }
    return was;
}

// ---- report / panic ------------------------------------------------------------------------------------------------
void OSReport(const char* msg, ...)
{
    char buffer[1024];
    va_list va;
    va_start(va, msg);
    vsnprintf(buffer, sizeof(buffer), msg, va);
    va_end(va);
    re4_diag_write(buffer);
    xsdk_log_write("re4 OSReport: %s", buffer);
    fputs(buffer, stderr);
}

// Explicit boot checkpoints use the same persistent log as the Xenon entry point.
void re4_boot_log(const char* message)
{
    re4_diag_write(message ? message : "(null)");
    xsdk_log_write("re4 boot: %s", message ? message : "(null)");
}

void OSPanic(const char* file, int line, const char* msg, ...)
{
    char buffer[1024];
    va_list va;
    va_start(va, msg);
    vsnprintf(buffer, sizeof(buffer), msg, va);
    va_end(va);
    re4_diag_write(buffer);
    xsdk_log_write("re4 PANIC %s:%d: %s", file, line, buffer);
    fprintf(stderr, "\nPANIC %s:%d: %s\n", file, line, buffer);
    abort();
}

// ---- stopwatch, alarm, modules (REL overlays are linked statically), console, fonts -------------------------------------
void OSInitStopwatch(OSStopwatch* sw, char* name) { memset(sw, 0, sizeof(*sw)); }
void OSStartStopwatch(OSStopwatch*) {}
void OSStopStopwatch(OSStopwatch*) {}
void OSResetStopwatch(OSStopwatch* sw) { memset(sw, 0, sizeof(*sw)); }
void OSInitAlarm(void) {}
struct RelEntry {
    unsigned id;
    const char* name;
    void (*prolog)(void);
    void (*epilog)(void);
    void (*unresolved)(void);
};
extern const RelEntry g_relTable[];   // generated by tools/xenon/gen_modules.py
extern const int g_relTableCount;

// The REL's bytes were read from the disc into memory as before, but its code is already in the XEX: look the module up by id
// and give the game its entry points where OSLink would have put the relocated addresses (DLL_PROLOG reads header->prolog).
BOOL OSLink(OSModuleInfo* info, void*)
{
    for (int i = 0; i < g_relTableCount; i++) {
        if (g_relTable[i].id == info->id) {
            OSModuleHeader* h = (OSModuleHeader*) info;
            h->prolog = (u32) g_relTable[i].prolog;
            h->epilog = (u32) g_relTable[i].epilog;
            h->unresolved = (u32) g_relTable[i].unresolved;
            return TRUE;
        }
    }
    fprintf(stderr, "OSLink: module id %u is not in the static table\n", (unsigned) info->id);
    return FALSE;
}
BOOL OSUnlink(OSModuleInfo*) { return TRUE; }
u32 OSGetConsoleType(void) { return 0x00000002; }
u32 OSGetConsoleSimulatedMemSize(void) { return 0x01800000; }
BOOL OSGetResetButtonState(void) { return FALSE; }
void OSResetSystem(int, u32, BOOL) { exit(0); }
void OSSetSaveRegion(void*, void*) {}
BOOL OSInitFont(OSFontHeader*) { return FALSE; }
u16 OSGetFontEncode(void) { return 0; }
char* OSGetFontTexture(const char* string, void**, s32*, s32*, s32*) { return (char*) string; }

static u32 g_soundMode, g_progressive;
u32 OSGetSoundMode(void) { return g_soundMode; }
void OSSetSoundMode(u32 m) { g_soundMode = m; }
u32 OSGetProgressiveMode(void) { return g_progressive; }
void OSSetProgressiveMode(u32 on) { g_progressive = on; }

BOOL DBIsDebuggerPresent(void) { return FALSE; }
OSThread* GXSetCurrentGXThread(void) { return OSGetCurrentThread(); }   // one GX thread: whoever holds the baton

// ---- GameCube performance counters ---------------------------------------------------------------------------------
u32 PPCMfpmc1() { return 0; }
void PPCMtmmcr0(u32) {}
void PPCMtmmcr1(u32) {}
void PPCMtpmc1(u32) {}
void PPCMtpmc2(u32) {}
void PPCMtpmc3(u32) {}
void PPCMtpmc4(u32) {}
void PPCSync() {}

// ---- audio RAM / audio interface (the game's own audio goes through audio_stubs.cpp, silent for now) --------------------
void AIInit(u8*) {}
void AIReset(void) {}
u32 ARGetBaseAddress(void) { return 0x4000; }
void ARQFlushQueue(void) {}

// ---- video interface: Aurora draws the frames; these only pace the game -----------------------------------------------
static VIRetraceCallback g_postRetrace;
static u32 g_field;
u32 VIGetDTVStatus(void) { return 1; }
u32 VIGetNextField(void) { return g_field; }
void VISetBlack(BOOL) {}
// The game calls this once per presented frame (Render_swap): close the Aurora frame and open the next one.
extern "C++" void re4_frame_boundary();
void VISetNextFrameBuffer(void*) { re4_frame_boundary(); }
VIRetraceCallback VISetPostRetraceCallback(VIRetraceCallback cb)
{
    VIRetraceCallback old = g_postRetrace;
    g_postRetrace = cb;
    return old;
}

void VIWaitForRetrace(void)
{
    // Aurora's present (vsync) paces the real frames; this short sleep only keeps boot-time waits from spinning.
    struct timespec ts = {0, 2000000};
    nanosleep(&ts, NULL);
    g_field ^= 1;
    if (g_postRetrace) {
        g_postRetrace(0);
    }
}

}  // extern "C"
