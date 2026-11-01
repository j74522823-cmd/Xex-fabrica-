Headers from SN Systems ProDG for Nintendo GameCube v3.9.3 (`include/` of the install): newlib 1.8.2 libc
headers, the GCC 2.95 ginclude headers (stdarg.h, stddef.h, va-ppc.h) and a few C++ headers. They are what the
original build found through the compiler's default include path.

tools/ngccc.py puts this directory in C_INCLUDE_PATH / CPLUS_INCLUDE_PATH, so it is searched after every -I
directory: a header of the same name in include/ or src/ takes precedence.

Licensing (from the notices in the files; SN's GnuSrcNGC.txt lists the GNU parts of ProDG as GPL/LGPL/newlib
with the source published):
- newlib headers: permissive licenses (Berkeley, Cygnus, AT&T, Sun, HP, AMD and others), all listed in
  COPYING.NEWLIB, none copyleft.
- GCC and libstdc++ headers: ansidecl.h (GPL v2 or later), new / exception / typeinfo (FSF copyright), va-ppc.h
  (GCC's file with SN's va_start change, marked as SN copyright but a GCC derivative), stdarg.h and stddef.h.
- machine/setjmp-dj.h and sys/stat-dj.h are DJ Delorie's: their notice requires a verbatim copy of "copying.dj"
  to accompany them. Nothing includes them.

Left out: SN_PS.h and libsn.h (SN Systems' own headers, not under the licenses above).
