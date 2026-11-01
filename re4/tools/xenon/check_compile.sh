#!/bin/bash
# Compile-checks every RE4 unit outside src/lib against Aurora's headers with the host GCC (-m32, -c).
# Usage: tools/xenon/check_compile.sh <aurora-xenon checkout> <out dir>
# NOTE: units with PowerPC inline asm (register variables bound to fr*/r*) cannot be judged by an x86 compiler; they show
# up as "constraint"/"register specified" errors. Run this again with the xsdk powerpc-xsdk-elf-g++ for the real answer.
set -u
A="$(realpath "$1")"; OUT="$(realpath -m "$2")"; mkdir -p "$OUT"
STUB="$OUT/_stub"; mkdir -p "$STUB/gnu"; touch "$STUB/gnu/stubs-32.h"   # no gcc-multilib needed for -c
cd "$(dirname "$0")/../.."
one() { src="$1"; b=$(echo "$src" | tr '/' '_')
  case "$src" in *.c) cc=gcc; std=gnu11;; *) cc=g++; std=gnu++17;; esac
  $cc -m32 -idirafter "$STUB" -idirafter /usr/include/x86_64-linux-gnu -idirafter /usr/include/x86_64-linux-gnu/c++/13 \
      -c -O0 -std=$std -fpermissive -w -DBUILD_VERSION=1 -DVERSION_G4BE08 -DNDEBUG=1 -DAURORA -DTARGET_PC \
      -I"$A/include" -Iinclude -Isrc "$src" -o "$OUT/$b.o" > "$OUT/$b.log" 2>&1
  echo "$src $?" >> "$OUT/_status.txt"; }
export -f one; export A OUT STUB; : > "$OUT/_status.txt"
find src -path src/lib -prune -o \( -name '*.c' -o -name '*.cpp' \) -print | grep -Ev -f tools/xenon/excluded.txt | xargs -P "$(nproc)" -I{} bash -c 'one {}'
echo "ok: $(grep -c ' 0$' "$OUT/_status.txt")  fail: $(grep -vc ' 0$' "$OUT/_status.txt")"
