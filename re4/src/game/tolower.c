/* newlib libc/ctype/tolower.c */
#include "newlib_local.h"

/* ASCII upper -> lower case. */
int tolower(int c)
{
    return isupper(c) ? (c) - 'A' + 'a' : c;
}
