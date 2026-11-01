/* newlib libc/ctype/isdigit.c */
#include "newlib_local.h"

/* ctype table lookup for '0'..'9'. */
int isdigit(int c)
{
    return ((_ctype_ + 1)[c] & _N);
}
