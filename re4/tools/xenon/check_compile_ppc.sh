#!/bin/bash
# Compile-only check of every RE4 unit outside src/lib with xsdk's real PowerPC compiler.
# Usage: tools/xenon/check_compile_ppc.sh <toolchain dir (~/xsdk-gcc)> <aurora-xenon checkout> <out dir>
# Env: CC / CXX override the compilers (e.g. for a smoke test on the host); LIMIT=N checks only the first N units.
set -uo pipefail
if [ "$#" -ne 3 ]; then
  echo "Uso: $0 <xsdk-gcc dir> <aurora-xenon checkout> <out dir>" >&2
  exit 2
fi
TC="$1"; A="$(realpath "$2")"; OUT="$(realpath -m "$3")"; mkdir -p "$OUT"
if [ ! -x "$TC/bin/powerpc-xsdk-elf-gcc" ] || [ ! -x "$TC/bin/powerpc-xsdk-elf-g++" ]; then
  echo "ERRO: compiladores do xsdk nao encontrados em $TC/bin" >&2
  exit 2
fi
if [ ! -d "$A/include" ]; then
  echo "ERRO: headers do aurora-xenon nao encontrados em $A/include" >&2
  exit 2
fi
cd "$(dirname "$0")/../.."
export CC="${CC:-$TC/bin/powerpc-xsdk-elf-gcc}" CXX="${CXX:-$TC/bin/powerpc-xsdk-elf-g++}" A OUT
one() { src="$1"; b=$(echo "$src" | tr '/' '_')
  case "$src" in *.c) cc="$CC"; std=gnu11;; *) cc="$CXX"; std=gnu++17;; esac
  $cc -c -O0 -std=$std -fpermissive -w -DBUILD_VERSION=1 -DVERSION_G4BE08 -DNDEBUG=1 -DAURORA -DTARGET_PC \
      -I"$A/include" -Iinclude -Isrc "$src" -o "$OUT/$b.o" > "$OUT/$b.log" 2>&1
  echo "$src $?" >> "$OUT/_status.txt"; }
export -f one; : > "$OUT/_status.txt"
list=$(find src -path src/lib -prune -o \( -name '*.c' -o -name '*.cpp' \) -print | grep -Ev -f tools/xenon/excluded.txt | sort)
[ -n "${LIMIT:-}" ] && list=$(echo "$list" | head -n "$LIMIT")
echo "$list" | xargs -P "$(nproc)" -I{} bash -c 'one {}'
ok=$(grep -c ' 0$' "$OUT/_status.txt"); fail=$(grep -vc ' 0$' "$OUT/_status.txt")
{
  echo "RE4 -> Xbox 360 compile check ($($CXX --version | head -1))"
  echo "ok: $ok   fail: $fail"; echo
  echo "== falhas por primeira mensagem de erro =="
  python3 - "$OUT" <<'PY'
import sys,re,collections
out=sys.argv[1]; c=collections.defaultdict(list)
for l in open(out+'/_status.txt'):
    f,rc=l.split()
    if rc=='0': continue
    log=open(out+'/'+f.replace('/','_')+'.log',errors='ignore').read()
    e=[x for x in log.splitlines() if 'error' in x]
    k=re.sub(r'\d+','N',re.sub(r"'[^']*'","X",e[0].split('error',1)[-1])) if e else 'sem mensagem (crash/assembler?)'
    c[k].append(f)
for k,v in sorted(c.items(), key=lambda kv:-len(kv[1])):
    print(f"{len(v):4d}  {k.strip()[:100]}"); print("      ex:", ", ".join(v[:4]))
print("\n== lista completa =="); 
for l in open(out+'/_status.txt'):
    f,rc=l.split()
    if rc!='0': print(f)
PY
} > "$OUT/summary.txt"
head -40 "$OUT/summary.txt"
if [ "$fail" -gt 0 ]; then
  echo "ERRO: $fail unidade(s) falharam; veja os logs em $OUT." >&2
  exit 1
fi
