/* newlib libc/stdlib/atof.c */
#include "newlib_local.h"

/* String to double (the game parses debug config values with it). */
double atof(const char *s)
{
    return strtod(s, NULL);
}
