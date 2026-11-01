#!/usr/bin/env python3
"""Write the copy of a compiled object that objdiff compares against the split object.

objdiff scores a data section as matched only when its raw bytes equal the target's and every symbol
of the target ends where a symbol of ours ends. Two properties of our toolchain make that impossible
for a byte-identical unit:
  * NgcAs/MWCC store the addend of a `.section+off` relocation in place (`.4byte .rodata+0x18` holds
    0x18) where dtk's split object holds 0 and carries `lbl+0`; the linker uses the RELA addend, so
    the DOL is the same either way, but the raw bytes differ at every such relocation;
  * string literals and constant pools have no symbol in a GCC/MWCC object, and objdiff compares a data
    section only up to the end of its last symbol, so a unit whose .rodata ends with strings compares
    a prefix of the section against the target's whole section.
This tool copies the compiled object with the bytes under every data relocation zeroed and, for the
bytes of a data section that none of our symbols covers, the target's own (visible) symbols added as
locals, so both sides carry the same symbol boundaries there and a relocation into a pool resolves to
the same symbol+addend on both sides. The linker never sees this copy: it is only the base_path of
objdiff.json.

usage: objdiff_base.py <split object> <compiled object> <output>
"""
import struct
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from strip_unused import Elf, SHT_RELA  # noqa: E402

SHT_PROGBITS = 1
SHF_ALLOC, SHF_EXECINSTR = 0x2, 0x4
RELOC_BYTES = {1: 4, 4: 2, 5: 2, 6: 2, 10: 4, 11: 4}  # ADDR32, ADDR16_LO/HI/HA, REL24, REL14


def visible_symbols(elf):
    """{section index: [(offset, size, name)]} of the visible sized symbols (what objdiff pairs)."""
    symtab = elf.index(".symtab")
    strs = elf.contents[elf.sections[symtab][6]]
    out = {}
    for o in range(0, len(elf.contents[symtab]), 16):
        st_name, st_value, st_size, st_info, st_other, st_shndx = struct.unpack(">IIIBBH", elf.contents[symtab][o:o + 16])
        if not st_name or not st_size or (st_info & 0xF) == 3 or st_other & 3 or not (0 < st_shndx < elf.shnum):
            continue
        out.setdefault(st_shndx, []).append((st_value, st_size, strs[st_name:strs.index(b"\0", st_name)].decode()))
    return out


def main():
    target = Elf(open(sys.argv[1], "rb").read())
    elf = Elf(open(sys.argv[2], "rb").read())
    target_syms = {target.names[i]: v for i, v in visible_symbols(target).items()}
    own_syms = visible_symbols(elf)
    symtab = elf.index(".symtab")
    strtab = elf.sections[symtab][6]
    new_syms = []  # (name, value, size, shndx)
    for i, sh in enumerate(elf.sections):
        if sh[1] != SHT_PROGBITS or not (sh[2] & SHF_ALLOC) or sh[2] & SHF_EXECINSTR or elf.names[i].startswith(".gnu.linkonce.t"):
            continue
        # 1. bytes under relocations: 0, as in the split object
        for j, rsh in enumerate(elf.sections):
            if rsh[1] != SHT_RELA or rsh[7] != i:
                continue
            for o in range(0, len(elf.contents[j]), 12):
                r_offset, r_info = struct.unpack(">II", elf.contents[j][o:o + 8])
                n = RELOC_BYTES.get(r_info & 0xFF, 0)
                elf.contents[i][r_offset:r_offset + n] = b"\0" * n
        # 2. anonymous data: the target's symbols wherever none of ours covers the bytes (a reloc into
        #    it then resolves to the same symbol+addend on both sides)
        own = sorted((v, v + sz) for v, sz, _ in own_syms.get(i, []))
        for value, size, name in sorted(target_syms.get(elf.names[i], [])):
            if value + size > len(elf.contents[i]):
                continue
            if any(a < value + size and value < b for a, b in own):
                continue
            new_syms.append((name, value, size, i))
    if new_syms:
        syms = [list(struct.unpack(">IIIBBH", elf.contents[symtab][o:o + 16])) for o in range(0, len(elf.contents[symtab]), 16)]
        first_global = elf.sections[symtab][7]
        strs = elf.contents[strtab]
        inserted = []
        for name, value, size, shndx in new_syms:
            inserted.append([len(strs), value, size, 1, 0, shndx])  # STT_OBJECT, STB_LOCAL, STV_DEFAULT
            strs += name.encode() + b"\0"
        syms[first_global:first_global] = inserted
        elf.contents[symtab] = bytearray().join(struct.pack(">IIIBBH", *s) for s in syms)
        elf.sections[symtab][7] = first_global + len(inserted)
        for j, rsh in enumerate(elf.sections):  # relocations index symbols: shift the globals
            if rsh[1] != SHT_RELA or rsh[6] != symtab:
                continue
            body = elf.contents[j]
            for o in range(0, len(body), 12):
                r_info, = struct.unpack_from(">I", body, o + 4)
                if (r_info >> 8) >= first_global:
                    struct.pack_into(">I", body, o + 4, r_info + (len(inserted) << 8))
    elf.write(sys.argv[3])


if __name__ == "__main__":
    main()
