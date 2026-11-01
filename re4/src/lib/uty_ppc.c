/* CRI UTY GameCube helpers (uty_ppc.c): save/restore of the six graphics quantisation registers
 * GQR2..GQR7 around the paired-single decoder kernels (MPV_DecodeFrmSj), so the game's own GQR
 * setup survives a frame decode. Hand-written asm functions. */
#include "cri_xpt.h"

typedef struct {
	Uint32 pad[2];
	Uint32 gqr[6];
} UTY_GQR;

// Restores GQR2..7 from the save block.
asm void UTY_PopGqr(register UTY_GQR *gqr)
{
	nofralloc
	lwz r0, 8(r3)
	lwz r4, 12(r3)
	lwz r5, 16(r3)
	lwz r6, 20(r3)
	lwz r7, 24(r3)
	lwz r3, 28(r3)
	mtspr 914, r0
	mtspr 915, r4
	mtspr 916, r5
	mtspr 917, r6
	mtspr 918, r7
	mtspr 919, r3
	blr
}

// Saves GQR2..7 into the save block.
asm void UTY_PushGqr(register UTY_GQR *gqr)
{
	nofralloc
	mfspr r0, 914
	mfspr r4, 915
	mfspr r5, 916
	mfspr r6, 917
	mfspr r7, 918
	mfspr r8, 919
	stw r0, 8(r3)
	stw r4, 12(r3)
	stw r5, 16(r3)
	stw r6, 20(r3)
	stw r7, 24(r3)
	stw r8, 28(r3)
	blr
}
