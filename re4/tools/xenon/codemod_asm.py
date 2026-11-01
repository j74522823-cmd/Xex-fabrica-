#!/usr/bin/env python3
"""Strips the compiler-matching asm hacks from the game sources so a modern GCC (xsdk's powerpc-xsdk-elf-g++) can build them.

 1. `register T x asm("r0"|"fr12"...)`   -> `T x`        (register pinning used to reproduce the SN compiler's allocation)
 2. `asm("" : ... );` with an empty template and no "memory" clobber (codeless scheduling fillers, "COMPILER-DIFF")  -> removed
 3. `PSQ_L_U8_TO(dst, p)` macro (Gekko paired-single psq_l; Xenon has no paired singles) -> plain u8 -> f32 conversion
Idempotent. Usage: tools/xenon/codemod_asm.py [--dry]
"""
import re, sys, pathlib
dry = '--dry' in sys.argv
root = pathlib.Path(__file__).resolve().parents[2]
pin = re.compile(r'\bregister\s+([A-Za-z_][\w:<>\s\*]*?)\s*(\w+)\s+asm\s*\(\s*"[a-z]+\d+"\s*\)')
filler = re.compile(r'^[ \t]*asm\s*\(\s*""\s*:[^;]*\)\s*;[ \t]*(//[^\n]*)?\n', re.M)
psq = re.compile(r'#define\s+PSQ_L_U8_TO\(dst,\s*p\)\s+asm\s+volatile\([^\n]*\)')
stats = {'pin': 0, 'filler': 0, 'psq': 0, 'files': 0}
for p in list((root / 'src').rglob('*.cpp')) + list((root / 'src').rglob('*.c')):
    if 'src/lib/' in p.as_posix():
        continue
    s = p.read_text(errors='surrogateescape'); o = s
    s, n1 = pin.subn(lambda m: f'{m.group(1).strip()} {m.group(2)}', s)
    def keep(m):
        return m.group(0) if 'memory' in m.group(0) else ''
    s2 = filler.sub(keep, s); n2 = len(filler.findall(s)) - len(filler.findall(s2)) if False else (len(filler.findall(s)) - len([1 for m in filler.finditer(s) if 'memory' in m.group(0)]))
    s = s2
    s, n3 = psq.subn('#define PSQ_L_U8_TO(dst, p) ((dst) = (f32) *(const u8*) (p))   /* was psq_l (Gekko only) */', s)
    if s != o:
        stats['files'] += 1; stats['pin'] += n1; stats['filler'] += n2; stats['psq'] += n3
        if not dry:
            p.write_text(s, errors='surrogateescape')
print(stats)
