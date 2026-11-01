/* va_list for ProDG-compiled game and libc code: the compiler's own stdarg.h (include/prodg/va-ppc.h,
 * SN's version with its struct-copy va_start). The newlib vf* units were built with the memcpy form in C. */
#ifndef VA_PPC_H
#define VA_PPC_H

#include <stdarg.h>

#ifndef __cplusplus
#undef va_start
#define va_start(AP, LASTARG) \
    (__builtin_next_arg(LASTARG), __builtin_memcpy((AP), __builtin_saveregs(), sizeof(__gnuc_va_list)))
#endif

#endif
