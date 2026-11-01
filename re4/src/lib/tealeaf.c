/* SN Systems ProDG libsn (tealeaf): __cvt_fp2unsigned, CodeWarrior-named 64-bit runtime aliases
 * branching to libgcc, and the MWCC-ABI __va_arg. Hand-written (cpp-preprocessed) assembly in the
 * original library (libsn.a tealeaf.o carries a `tea151.tmp` FILE symbol like proview/ppcdown, the C
 * objects carry `<name>.c`); the functions are whole-function asm() bodies, reproduced from the split
 * object. */
#include "asm_regs.h"

asm("	.text\n"
    "	.balign 4\n");

/* float -> unsigned 32-bit conversion (CodeWarrior runtime name): values >= 2^31 are converted after subtracting 2^31 and the top bit is put back; the CRI libraries (compiled with MWCC) call it. */
/* .text:0x0 | 0x80065854 | size: 0x48 */
asm("	.globl __cvt_fp2unsigned\n"
    "	.type __cvt_fp2unsigned,@function\n"
    "__cvt_fp2unsigned:\n"
    "	stwu r1, -0x10(r1)\n"
    "	lis r9, lbl_80225C60@ha\n"
    "	addi r9, r9, lbl_80225C60@l\n"
    "	lfd f0, 0x0(r9)\n"
    "	fcmpu cr0, f1, f0\n"
    "	cror un, eq, gt\n"
    "	bso .L_80065880\n"
    "	fctiwz f0, f1\n"
    "	stfd f0, 0x8(r1)\n"
    "	lwz r3, 0xc(r1)\n"
    "	b .L_80065894\n"
    ".L_80065880:\n"
    "	fsub f0, f1, f0\n"
    "	fctiwz f13, f0\n"
    "	stfd f13, 0x8(r1)\n"
    "	lwz r3, 0xc(r1)\n"
    "	xoris r3, r3, 0x8000\n"
    ".L_80065894:\n"
    "	addi r1, r1, 0x10\n"
    "	blr\n"
    "	.size __cvt_fp2unsigned,.-__cvt_fp2unsigned\n");

/* 64-bit unsigned shift right: alias branching to libgcc's __lshrdi3. */
/* .text:0x48 | 0x8006589C | size: 0x4 */
asm("	.globl __shr2u\n"
    "	.type __shr2u,@function\n"
    "__shr2u:\n"
    "	b __lshrdi3\n"
    "	.size __shr2u,.-__shr2u\n");

/* 64-bit signed divide: alias branching to libgcc's __divdi3 (MWCC runtime name used by the CRI code). */
/* .text:0x4C | 0x800658A0 | size: 0x4 */
asm("	.globl __div2i\n"
    "	.type __div2i,@function\n"
    "__div2i:\n"
    "	b __divdi3\n"
    "	.size __div2i,.-__div2i\n");

/* 64-bit shift left: alias to __ashldi3. */
/* .text:0x50 | 0x800658A4 | size: 0x4 */
asm("	.globl __shl2i\n"
    "	.type __shl2i,@function\n"
    "__shl2i:\n"
    "	b __ashldi3\n"
    "	.size __shl2i,.-__shl2i\n");

/* 64-bit signed remainder: alias to __moddi3 (kept linked by crt0's LinkFiddle). */
/* .text:0x54 | 0x800658A8 | size: 0x4 */
asm("	.globl __mod2i\n"
    "	.type __mod2i,@function\n"
    "__mod2i:\n"
    "	b __moddi3\n"
    "	.size __mod2i,.-__mod2i\n");

/* 64-bit signed shift right: alias to __ashrdi3. */
/* .text:0x58 | 0x800658AC | size: 0x4 */
asm("	.globl __shr2i\n"
    "	.type __shr2i,@function\n"
    "__shr2i:\n"
    "	b __ashrdi3\n"
    "	.size __shr2i,.-__shr2i\n");

/* 64-bit unsigned divide: alias to __udivdi3. */
/* .text:0x5C | 0x800658B0 | size: 0x4 */
asm("	.globl __div2u\n"
    "	.type __div2u,@function\n"
    "__div2u:\n"
    "	b __udivdi3\n"
    "	.size __div2u,.-__div2u\n");

/* 64-bit unsigned remainder: alias to __umoddi3. */
/* .text:0x60 | 0x800658B4 | size: 0x4 */
asm("	.globl __mod2u\n"
    "	.type __mod2u,@function\n"
    "__mod2u:\n"
    "	b __umoddi3\n"
    "	.size __mod2u,.-__mod2u\n");

/* CodeWarrior-ABI va_arg helper: fetches the next variadic argument of the given class (GPR / FPR / overflow area) from an MWCC va_list; used by the CRI code's vsprintf error formatting. */
/* .text:0x64 | 0x800658B8 | size: 0xF4 */
asm("	.globl __va_arg\n"
    "	.type __va_arg,@function\n"
    "__va_arg:\n"
    "	clrlwi r0, r4, 24\n"
    "	lbz r6, 0x0(r3)\n"
    "	cmplwi r0, 0x4\n"
    "	addi r7, r3, 0x0\n"
    "	extsb r6, r6\n"
    "	li r5, 0x8\n"
    "	li r8, 0x4\n"
    "	li r9, 0x1\n"
    "	li r10, 0x0\n"
    "	li r11, 0x0\n"
    "	li r12, 0x4\n"
    "	bne .L_80065904\n"
    "	lwz r4, 0x4(r3)\n"
    "	addi r0, r4, 0xf\n"
    "	clrrwi r4, r0, 4\n"
    "	addi r0, r4, 0x10\n"
    "	stw r0, 0x4(r3)\n"
    "	mr r3, r4\n"
    "	blr\n"
    ".L_80065904:\n"
    "	cmplwi r0, 0x3\n"
    "	bne .L_80065924\n"
    "	lbz r6, 0x1(r3)\n"
    "	addi r7, r3, 0x1\n"
    "	li r8, 0x8\n"
    "	extsb r6, r6\n"
    "	li r11, 0x20\n"
    "	li r12, 0x8\n"
    ".L_80065924:\n"
    "	clrlwi r0, r4, 24\n"
    "	cmplwi r0, 0x2\n"
    "	bne .L_80065948\n"
    "	clrlwi. r0, r6, 31\n"
    "	li r8, 0x8\n"
    "	li r5, 0x7\n"
    "	beq .L_80065944\n"
    "	li r10, 0x1\n"
    ".L_80065944:\n"
    "	li r9, 0x2\n"
    ".L_80065948:\n"
    "	cmpw r6, r5\n"
    "	bge .L_80065970\n"
    "	add r6, r6, r10\n"
    "	lwz r5, 0x8(r3)\n"
    "	mullw r3, r6, r12\n"
    "	add r0, r6, r9\n"
    "	add r6, r11, r3\n"
    "	stb r0, 0x0(r7)\n"
    "	add r6, r5, r6\n"
    "	b .L_80065998\n"
    ".L_80065970:\n"
    "	li r0, 0x8\n"
    "	stb r0, 0x0(r7)\n"
    "	subi r0, r8, 0x1\n"
    "	nor r6, r0, r0\n"
    "	lwz r0, 0x4(r3)\n"
    "	add r5, r8, r0\n"
    "	subi r0, r5, 0x1\n"
    "	and r6, r6, r0\n"
    "	add r0, r6, r8\n"
    "	stw r0, 0x4(r3)\n"
    ".L_80065998:\n"
    "	clrlwi. r0, r4, 24\n"
    "	bne .L_800659A4\n"
    "	lwz r6, 0x0(r6)\n"
    ".L_800659A4:\n"
    "	mr r3, r6\n"
    "	blr\n"
    "	.size __va_arg,.-__va_arg\n");

/* 0x80225C60..0x80225C68 | size: 0x8 */
asm("	.rodata\n"
    "	.balign 8\n");

/* The 2^31 double constant of __cvt_fp2unsigned (.rodata). */
/* .rodata:0x0 | 0x80225C60 | size: 0x8 */
asm("	.type lbl_80225C60,@object\n"
    "lbl_80225C60:\n"
    "	.double 2147483648\n"
    "	.size lbl_80225C60,.-lbl_80225C60\n");
