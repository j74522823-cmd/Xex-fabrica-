/* newlib libc/string/strrchr.c */
#include "newlib_local.h"

/* Last occurrence of character i in s, NULL when absent. */
char *strrchr(const char *s, int i)
{
    const char *last = NULL;
    char c = i;

    while (*s) {
        if (*s == c) {
            last = s;
        }
        s++;
    }

    if (*s == c) {
        last = s;
    }

    return (char *)last;
}
