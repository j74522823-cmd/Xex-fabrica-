/* newlib libc/stdlib/atoi.c */
#include "newlib_local.h"

/* String to int, base 10. */
int atoi(const char *s)
{
    return (int)strtol(s, NULL, 10);
}
