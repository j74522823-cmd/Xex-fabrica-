/* Register and SPR names for the whole-function asm() units (src/lib/__start.c, eabi.c, tealeaf.c,
 * fileserver.c, ppcdown.c, proview.c, src/game/memset_2.cpp, yz2asm.cpp). NgcAs takes bare numbers
 * only; these `.set` constants give the units the r3/f1/GQR0/cr-bit spelling of include/macros.inc
 * (they never reach the symbol table). */
#ifndef ASM_REGS_H
#define ASM_REGS_H

asm("\t.set r0, 0\n\t.set r1, 1\n\t.set r2, 2\n\t.set r3, 3\n\t.set r4, 4\n\t.set r5, 5\n"
    "\t.set r6, 6\n\t.set r7, 7\n\t.set r8, 8\n\t.set r9, 9\n\t.set r10, 10\n\t.set r11, 11\n"
    "\t.set r12, 12\n\t.set r13, 13\n\t.set r14, 14\n\t.set r15, 15\n\t.set r16, 16\n\t.set r17, 17\n"
    "\t.set r18, 18\n\t.set r19, 19\n\t.set r20, 20\n\t.set r21, 21\n\t.set r22, 22\n\t.set r23, 23\n"
    "\t.set r24, 24\n\t.set r25, 25\n\t.set r26, 26\n\t.set r27, 27\n\t.set r28, 28\n\t.set r29, 29\n"
    "\t.set r30, 30\n\t.set r31, 31\n");

asm("\t.set f0, 0\n\t.set f1, 1\n\t.set f2, 2\n\t.set f3, 3\n\t.set f4, 4\n\t.set f5, 5\n"
    "\t.set f6, 6\n\t.set f7, 7\n\t.set f8, 8\n\t.set f9, 9\n\t.set f10, 10\n\t.set f11, 11\n"
    "\t.set f12, 12\n\t.set f13, 13\n\t.set f14, 14\n\t.set f15, 15\n\t.set f16, 16\n\t.set f17, 17\n"
    "\t.set f18, 18\n\t.set f19, 19\n\t.set f20, 20\n\t.set f21, 21\n\t.set f22, 22\n\t.set f23, 23\n"
    "\t.set f24, 24\n\t.set f25, 25\n\t.set f26, 26\n\t.set f27, 27\n\t.set f28, 28\n\t.set f29, 29\n"
    "\t.set f30, 30\n\t.set f31, 31\n");

asm("\t.set qr0, 0\n\t.set qr1, 1\n\t.set qr2, 2\n\t.set qr3, 3\n"
    "\t.set qr4, 4\n\t.set qr5, 5\n\t.set qr6, 6\n\t.set qr7, 7\n");

/* condition register fields and bits */
asm("\t.set cr0, 0\n\t.set cr1, 1\n\t.set cr2, 2\n\t.set cr3, 3\n"
    "\t.set cr4, 4\n\t.set cr5, 5\n\t.set cr6, 6\n\t.set cr7, 7\n"
    "\t.set lt, 0\n\t.set gt, 1\n\t.set eq, 2\n\t.set so, 3\n\t.set un, 3\n");

/* special purpose registers */
asm("\t.set XER, 1\n\t.set LR, 8\n\t.set CTR, 9\n\t.set DSISR, 18\n\t.set DAR, 19\n\t.set DEC, 22\n"
    "\t.set SDR1, 25\n\t.set SRR0, 26\n\t.set SRR1, 27\n"
    "\t.set SPRG0, 272\n\t.set SPRG1, 273\n\t.set SPRG2, 274\n\t.set SPRG3, 275\n"
    "\t.set EAR, 282\n\t.set PVR, 287\n"
    "\t.set IBAT0U, 528\n\t.set IBAT0L, 529\n\t.set IBAT1U, 530\n\t.set IBAT1L, 531\n"
    "\t.set IBAT2U, 532\n\t.set IBAT2L, 533\n\t.set IBAT3U, 534\n\t.set IBAT3L, 535\n"
    "\t.set DBAT0U, 536\n\t.set DBAT0L, 537\n\t.set DBAT1U, 538\n\t.set DBAT1L, 539\n"
    "\t.set DBAT2U, 540\n\t.set DBAT2L, 541\n\t.set DBAT3U, 542\n\t.set DBAT3L, 543\n"
    "\t.set GQR0, 912\n\t.set GQR1, 913\n\t.set GQR2, 914\n\t.set GQR3, 915\n"
    "\t.set GQR4, 916\n\t.set GQR5, 917\n\t.set GQR6, 918\n\t.set GQR7, 919\n"
    "\t.set HID2, 920\n\t.set WPAR, 921\n\t.set DMA_U, 922\n\t.set DMA_L, 923\n"
    "\t.set UMMCR0, 936\n\t.set UPMC1, 937\n\t.set UPMC2, 938\n\t.set USIA, 939\n"
    "\t.set UMMCR1, 940\n\t.set UPMC3, 941\n\t.set UPMC4, 942\n\t.set USDA, 943\n"
    "\t.set MMCR0, 952\n\t.set PMC1, 953\n\t.set PMC2, 954\n\t.set SIA, 955\n"
    "\t.set MMCR1, 956\n\t.set PMC3, 957\n\t.set PMC4, 958\n\t.set SDA, 959\n"
    "\t.set HID0, 1008\n\t.set HID1, 1009\n\t.set IABR, 1010\n\t.set DABR, 1013\n"
    "\t.set L2CR, 1017\n\t.set ICTC, 1019\n\t.set THRM1, 1020\n\t.set THRM2, 1021\n\t.set THRM3, 1022\n");

#endif
