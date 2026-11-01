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


# --- second pass: top-level section-switching asm used only for byte-matching (".section .data; .balign 8" ...) ---
def strip_section_asm(root='src'):
    import os, re
    pat = re.compile(r'^[ \t]*asm[ \t]*\("\.(?:section|data|text|rodata|balign|align)[^;\n]*?"\);[ \t]*\n', re.M)
    n = 0
    for d, _, fs in os.walk(root):
        for f in fs:
            if f.endswith(('.c', '.cpp')):
                p = os.path.join(d, f); s = open(p, errors='surrogateescape').read()
                s2, k = pat.subn('', s)
                if k:
                    open(p, 'w', errors='surrogateescape').write(s2); n += k
    print('section asm lines removed:', n)

if __name__ == '__main__' and len(__import__('sys').argv) > 1 and __import__('sys').argv[1] == 'sections':
    strip_section_asm()
