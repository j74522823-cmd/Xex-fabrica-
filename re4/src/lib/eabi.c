/* SN Systems ProDG libsn: EABI floating-point register save/restore helpers (_savefpr_14/_restfpr_14).
 * Hand-written assembly in the original library (no C form exists); the functions are whole-function
 * asm() bodies, reproduced from the split object. */
#include "asm_regs.h"

asm("	.text\n"
    "	.balign 4\n");

/* EABI helper: saves f14..f31 at negative offsets from r11 (entered at the label for the first register to save); GCC emits a call to it in prologues that use many FP registers. */
/* .text:0x0 | 0x8021C8B4 | size: 0x4C */
asm("	.globl _savefpr_14\n"
    "	.type _savefpr_14,@function\n"
    "_savefpr_14:\n"
    "	stfd f14, -0x90(r11)\n"
    "	stfd f15, -0x88(r11)\n"
    "	stfd f16, -0x80(r11)\n"
    "	stfd f17, -0x78(r11)\n"
    "	stfd f18, -0x70(r11)\n"
    "	stfd f19, -0x68(r11)\n"
    "	stfd f20, -0x60(r11)\n"
    "	stfd f21, -0x58(r11)\n"
    "	stfd f22, -0x50(r11)\n"
    "	stfd f23, -0x48(r11)\n"
    "	stfd f24, -0x40(r11)\n"
    "	stfd f25, -0x38(r11)\n"
    "	stfd f26, -0x30(r11)\n"
    "	stfd f27, -0x28(r11)\n"
    "	stfd f28, -0x20(r11)\n"
    "	stfd f29, -0x18(r11)\n"
    "	stfd f30, -0x10(r11)\n"
    "	stfd f31, -0x8(r11)\n"
    "	blr\n"
    "	.size _savefpr_14,.-_savefpr_14\n");

/* EABI helper: restores f14..f31 from r11 and returns. */
/* .text:0x4C | 0x8021C900 | size: 0x4C */
asm("	.globl _restfpr_14\n"
    "	.type _restfpr_14,@function\n"
    "_restfpr_14:\n"
    "	lfd f14, -0x90(r11)\n"
    "	lfd f15, -0x88(r11)\n"
    "	lfd f16, -0x80(r11)\n"
    "	lfd f17, -0x78(r11)\n"
    "	lfd f18, -0x70(r11)\n"
    "	lfd f19, -0x68(r11)\n"
    "	lfd f20, -0x60(r11)\n"
    "	lfd f21, -0x58(r11)\n"
    "	lfd f22, -0x50(r11)\n"
    "	lfd f23, -0x48(r11)\n"
    "	lfd f24, -0x40(r11)\n"
    "	lfd f25, -0x38(r11)\n"
    "	lfd f26, -0x30(r11)\n"
    "	lfd f27, -0x28(r11)\n"
    "	lfd f28, -0x20(r11)\n"
    "	lfd f29, -0x18(r11)\n"
    "	lfd f30, -0x10(r11)\n"
    "	lfd f31, -0x8(r11)\n"
    "	blr\n"
    "	.size _restfpr_14,.-_restfpr_14\n");

/* Padding after _restfpr_14 up to the next 32-byte boundary (not a real function). */
/* .text:0x98 | 0x8021C94C | size: 0x14 */
asm("	.type gap_01_8021C94C_text,@function\n"
    "gap_01_8021C94C_text:\n"
    "	.4byte 0x00000000\n" /* invalid */
    "	.4byte 0x00000000\n" /* invalid */
    "	.4byte 0x00000000\n" /* invalid */
    "	.4byte 0x00000000\n" /* invalid */
    "	.4byte 0x00000000\n" /* invalid */
    "	.size gap_01_8021C94C_text,.-gap_01_8021C94C_text\n");
