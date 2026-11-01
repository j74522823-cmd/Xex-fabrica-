// Silent audio and video for the first 360 builds: the GameCube's AX / MIX / SYN / SEQ audio stack, the CRI ADX / Sofdec
// player and the debugger-link file calls (PC*) do nothing. Music and movies come later (as the project's plan says: convert
// the streams and play them through xsdk's audio); until then the game runs mute.
#include "dolphin/ax.h"
#include "dolphin/axart.h"
#include "dolphin/axfx.h"
#include "dolphin/mix.h"
#include "dolphin/seq.h"
#include "dolphin/syn.h"
#include "snd_sdk.h"
#include "mwply.h"
#include "sofdec.h"
#include "fileserver.h"

extern "C" {
void ADXM_ExecMain() {}
void ADXM_SetCbErr(void (*func)(void* obj, const char* msg), void* obj) {}
void AXARTInit(void) {}
void AXARTQuit(void) {}
void AXARTServiceSounds(void) {}
AXVPB* AXAcquireVoice(u32 priority, void (*callback)(void *), u32 userContext) { return (AXVPB*) 0; }
void AXFXChorusCallback(AXFX_BUFFERUPDATE* bufferUpdate, AXFX_CHORUS* chorus) {}
int AXFXChorusInit(AXFX_CHORUS* c) { return (int) 0; }
int AXFXChorusSettings(AXFX_CHORUS* c) { return (int) 0; }
int AXFXChorusShutdown(AXFX_CHORUS* c) { return (int) 0; }
void AXFXDelayCallback(AXFX_BUFFERUPDATE* bufferUpdate, AXFX_DELAY* delay) {}
int AXFXDelayInit(AXFX_DELAY* delay) { return (int) 0; }
int AXFXDelaySettings(AXFX_DELAY* delay) { return (int) 0; }
int AXFXDelayShutdown(AXFX_DELAY* delay) { return (int) 0; }
void AXFXReverbHiCallback(AXFX_BUFFERUPDATE* bufferUpdate, AXFX_REVERBHI* reverb) {}
void AXFXReverbHiCallbackDpl2(AXFX_BUFFERUPDATE_DPL2* bufferUpdate, AXFX_REVERBHI_DPL2* reverb) {}
int AXFXReverbHiInit(AXFX_REVERBHI* rev) { return (int) 0; }
int AXFXReverbHiInitDpl2(AXFX_REVERBHI_DPL2* reverb) { return (int) 0; }
int AXFXReverbHiSettings(AXFX_REVERBHI* rev) { return (int) 0; }
int AXFXReverbHiSettingsDpl2(AXFX_REVERBHI_DPL2* rev) { return (int) 0; }
int AXFXReverbHiShutdown(AXFX_REVERBHI* rev) { return (int) 0; }
int AXFXReverbHiShutdownDpl2(AXFX_REVERBHI_DPL2* reverb) { return (int) 0; }
void AXFXReverbStdCallback(AXFX_BUFFERUPDATE* bufferUpdate, AXFX_REVERBSTD* reverb) {}
int AXFXReverbStdInit(AXFX_REVERBSTD* rev) { return (int) 0; }
int AXFXReverbStdSettings(AXFX_REVERBSTD* rev) { return (int) 0; }
int AXFXReverbStdShutdown(AXFX_REVERBSTD* rev) { return (int) 0; }
void AXFXSetHooks(void* (*alloc)(u32), void (*free)(void*)) {}
void AXFreeVoice(AXVPB* p) {}
u32 AXGetDspCycles(void) { return (u32) 0; }
u32 AXGetMaxDspCycles(void) { return (u32) 0; }
void AXInitEx(u32 outputBufferMode) {}
void AXQuit(void) {}
void AXRegisterAuxACallback(void (*callback)(void*, void*), void* context) {}
void AXRegisterAuxBCallback(void (*callback)(void*, void*), void* context) {}
AXCallback AXRegisterCallback(AXCallback callback) { return (AXCallback) 0; }
void AXSetCompressor(u32 switch_) {}
void AXSetMode(u32 mode) {}
void AXSetVoiceAddr(AXVPB* p, AXPBADDR* addr) {}
void AXSetVoiceAdpcm(AXVPB* p, AXPBADPCM* adpcm) {}
void AXSetVoiceAdpcmLoop(AXVPB* p, AXPBADPCMLOOP* adpcmloop) {}
void AXSetVoiceEndAddr(AXVPB* p, u32 addr) {}
void AXSetVoiceLoop(AXVPB* p, u16 loop) {}
void AXSetVoiceLoopAddr(AXVPB* p, u32 addr) {}
void AXSetVoiceLpf(AXVPB* p, AXPBLPF* lpf) {}
void AXSetVoiceLpfCoefs(AXVPB* p, u16 a0, u16 b0) {}
void AXSetVoicePriority(AXVPB* p, u32 priority) {}
void AXSetVoiceSrc(AXVPB* p, AXPBSRC* src_) {}
void AXSetVoiceSrcRatio(AXVPB* p, f32 ratio) {}
void AXSetVoiceSrcType(AXVPB* p, u32 type) {}
void AXSetVoiceState(AXVPB* p, u16 state) {}
void AXSetVoiceType(AXVPB* p, u16 type) {}
void MIXInit(void) {}
void MIXInitChannel(AXVPB* axvpb, u32 mode, int input, int auxA, int auxB, int pan, int span, int fader) {}
void MIXQuit(void) {}
void MIXReleaseChannel(AXVPB* axvpb) {}
void MIXSetAuxA(AXVPB* p, int dB) {}
void MIXSetAuxB(AXVPB* p, int dB) {}
void MIXSetInput(AXVPB* p, int dB) {}
void MIXSetPan(AXVPB* p, int pan) {}
void MIXSetSPan(AXVPB* p, int span) {}
void MIXSetSoundMode(u32 mode) {}
void MIXUpdateSettings(void) {}
int PCclose(int fd) { return (int) -1; }
int PCcreat(const char* path, int mode) { return (int) -1; }
int PCinit() { return (int) -1; }
int PClseek(int fd, int offset, int whence) { return (int) -1; }
int PCopen(const char* path, int flags, int mode) { return (int) -1; }
int PCread(int fd, void* buf, int size) { return (int) -1; }
int PCwrite(int fd, const void* buf, int size) { return (int) -1; }
void SEQInit(void) {}
void SEQQuit(void) {}
void SEQRunAudioFrame(void) {}
u32 SYNGetActiveNotes(SYNSYNTH* synth) { return (u32) 0; }
void SYNInit(void) {}
void SYNInitSynth(SYNSYNTH* synth, void* wavetable, u32 aramBase, u32 zeroBase, u32 priorityVoiceAlloc, u32 priorityNoteOn, u32 priorityNoteRelease) {}
void SYNMidiInput(SYNSYNTH* synth, u8* input) {}
void SYNQuit(void) {}
void SYNQuitSynth(SYNSYNTH* synth) {}
void SYNRunAudioFrame(void) {}
void SYNSetMasterVolume(SYNSYNTH* synth, s32 dB) {}
int mwPlyCalcWorkCprmSfd(MWS_PLY_CPRM_SFD* prm) { return (int) 0; }
MWPLY mwPlyCreateSofdec(MWS_PLY_CPRM_SFD* prm) { return (MWPLY) 0; }
void mwPlyFxCnvFrmARGB8888(MWPLY hn, MWS_FRM* frm, void* buf) {}
void mwPlyFxCnvFrmY84C44(MWPLY hn, MWS_FRM* frm, void* ybuf, void* uvbuf) {}
void mwPlyFxSetOutBufPitchHeight(MWPLY hn, int pitch, int height) {}
void mwPlyFxSetOutBufSize(MWPLY hn, int width, int height) {}
void mwPlyGetCurFrm(MWPLY hn, MWS_FRM* frm) {}
void mwPlyGetHdrInf(void* buf, int size, MWS_SFD_HDRINF* info) {}
int mwPlyGetNumSkipDec(MWPLY hn) { return (int) 0; }
int mwPlyGetNumSkipDisp(MWPLY hn) { return (int) 0; }
void mwPlyInitSfdFx(MWS_PLY_INIT_SFD* prm) {}
void mwPlyRelCurFrm(MWPLY hn) {}

// Not found in a header of the project: the original declared them only in the unit that calls them.
void ADXGC_SetupDvdFs(int mode) {}
void ADXT_SetOutputMono(int sw) {}
}  // extern "C"
