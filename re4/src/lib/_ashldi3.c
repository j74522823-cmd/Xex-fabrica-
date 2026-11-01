/* libgcc: gcc 2.95.3 libgcc2.c section L_ashldi3.
 * __ashldi3: 64-bit shift left (long long << n). GCC calls it for every `long long` shift the game
 * and the newlib/CRI code perform; tealeaf's __shl2i alias hands the MWCC-built CRI objects to it. */
#define L_ashldi3
#include "libgcc2/libgcc2.c"
