#!/usr/bin/env python3
"""Make the data/bss symbols of the split (target) objects follow the compiled objects.

The debug build's Bio4.sym names no data, so config/<ver>/symbols.txt and the module symbol files carry
dtk's `lbl_...` placeholders for every data object and .bss variable, sized by dtk's analysis (a
placeholder swallows the alignment padding after it, a byte-wise accessed word becomes 3+1 bytes, a
static array may be split at each referenced offset). objdiff pairs symbols by name and scores .bss by
the (offset, size) layout of the visible symbols, so a byte-identical unit still shows .bss/.data below
100% in the progress report, and the target asm reads `lbl_80276805` where the source says `PlCapNum`.

For every matched unit (objdiff.json unit with a target, a source and `complete: true`), per section
(.bss/.sbss and .data/.rodata/.sdata/.sdata2), the target's symbols are made to agree with the
compiled object's visible symbols:
  * a target symbol at a compiled symbol's offset takes the compiled name and size (placeholders
    inside the compiled range are deleted, references to them become `sym+off`);
  * a compiled symbol with no target symbol at its offset is added;
  * a placeholder with no compiled symbol at its offset is deleted in .bss/.sbss (alignment padding:
    dtk fills it with a hidden gap symbol); in the data sections it stays (a string or pool the
    compiled object has no symbol for) unless it is zero bytes behind the compiled section's end
    (the split's alignment padding).
The edits of a section are applied only if every address any split object relocates against stays
inside a visible symbol (dtk resolves REL relocations through the symbol table before it fills gaps),
and only if no non-placeholder target symbol disagrees with the compiled object; otherwise the section
is reported and left alone.
A `name.NNN` static (gcc DECL_UID suffix, MWCC `name$NNN`) counts as already synced when the target
carries the same stem with any suffix (objdiff and strip_unused.py pair them that way), so re-syncing
after an unrelated source edit changes nothing. Names never override an existing *global* of the same
name in the same symbol file (locals may repeat); MWCC `@NNN` pool names are never written (objdiff
pairs those by content). sym_map.tsv is kept in step (name/size column, rows added and removed).

usage: sync_data_symbols.py [--dry-run] [-q] [<compiled .o> ...]
       (no objects: every unit of objdiff.json; then `python3 configure.py && ninja`)
"""
import bisect
import json
import os
import re
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from sync_symbols import atomic_write  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VER = os.environ.get("RE4_VERSION", "G4BE08")
CFG = os.path.join(ROOT, "config", VER)
BUILD = os.path.join(ROOT, "build", VER)
BSS_SECTIONS = {".bss", ".sbss", ".sbss2"}
DATA_SECTIONS = {".data", ".rodata", ".sdata", ".sdata2"}
SYM_RE = re.compile(r"^(\S+) = (\.\w+):0x([0-9A-F]+); // type:(\w+) size:0x([0-9A-F]+) scope:(\w+)(.*)$")
PLACEHOLDER_RE = re.compile(r"^(lbl_|fn_|gap_|pad_|jumptable_)")


def is_placeholder(name):
    return bool(PLACEHOLDER_RE.match(name))


def stem_of(name):
    """`noY.264` (gcc) / `buf$75` (MWCC) -> `noY` / `buf`; other names unchanged."""
    m = re.match(r"^(.*)[.$]\d+$", name)
    return m.group(1) if m else name


def same_static(a, b):
    """True when both are the same static under another DECL_UID suffix."""
    return bool(re.search(r"[.$]\d+$", a) or re.search(r"[.$]\d+$", b)) and stem_of(a) == stem_of(b)


class Elf:
    """ELF32 big-endian object: visible sized symbols per section and relocation targets."""

    def __init__(self, path):
        data = open(path, "rb").read()
        shoff, = struct.unpack_from(">I", data, 0x20)
        shentsize, shnum, shstrndx = struct.unpack_from(">HHH", data, 0x2E)
        shdrs = [struct.unpack_from(">IIIIIIIIII", data, shoff + i * shentsize) for i in range(shnum)]

        def cstr(off, idx):
            end = data.index(b"\0", off + idx)
            return data[off + idx:end].decode()

        self.names = [cstr(shdrs[shstrndx][4], sh[0]) for sh in shdrs]
        self.sizes = {self.names[i]: sh[5] for i, sh in enumerate(shdrs)}
        self.data = {self.names[i]: data[sh[4]:sh[4] + sh[5]] for i, sh in enumerate(shdrs) if sh[1] == 1}
        self.syms = {}  # section -> {offset: (size, name, bind)}: what objdiff pairs and lays out
        self.symtab = []  # (name, value, shndx)
        symtab = next(sh for sh in shdrs if sh[1] == 2)
        strtab = shdrs[symtab[6]]
        for off in range(symtab[4], symtab[4] + symtab[5], 16):
            st_name, st_value, st_size, st_info, st_other, st_shndx = struct.unpack_from(">IIIBBH", data, off)
            name = cstr(strtab[4], st_name) if st_name else ""
            if (st_info & 0xF) == 3 and st_shndx < shnum:
                name = self.names[st_shndx]
            self.symtab.append((name, st_value, st_shndx))
            if not st_name or not st_size or (st_info & 0xF) == 3 or st_shndx == 0 or st_shndx >= shnum:
                continue
            if st_other & 3:  # hidden/internal visibility: objdiff hides it (dtk's gap_ symbols)
                continue
            self.syms.setdefault(self.names[st_shndx], {})[st_value] = (st_size, name, st_info >> 4)
        self.relocs = []  # (symbol name, section name of a defined target or None, value, addend)
        for i, sh in enumerate(shdrs):
            if sh[1] != 4:
                continue
            for off in range(sh[4], sh[4] + sh[5], 12):
                r_offset, r_info, r_addend = struct.unpack_from(">IIi", data, off)
                name, value, shndx = self.symtab[r_info >> 8]
                sec = self.names[shndx] if 0 < shndx < shnum else None
                self.relocs.append((name, sec, value, r_addend))


class Entry:
    __slots__ = ("index", "name", "section", "address", "size", "scope")

    def __init__(self, index, m):
        self.index, self.name, self.section = index, m.group(1), m.group(2)
        self.address, self.size, self.scope = int(m.group(3), 16), int(m.group(5), 16), m.group(6)


class SymbolFile:
    """symbols.txt + sym_map.tsv + splits.txt of the DOL (module None) or of one REL module."""

    def __init__(self, module):
        d = CFG if module is None else os.path.join(CFG, "modules", module)
        self.module = module
        self.path = os.path.join(d, "symbols.txt")
        self.map_path = os.path.join(d, "sym_map.tsv")
        self.lines = open(self.path).read().splitlines()
        self.map_rows = open(self.map_path).read().splitlines()
        self.by_section = {}  # section -> sorted [(address, Entry)]
        self.by_name = {}
        self.globals = set()
        for i, l in enumerate(self.lines):
            m = SYM_RE.match(l)
            if m:
                e = Entry(i, m)
                self.by_section.setdefault(e.section, []).append((e.address, e))
                self.by_name.setdefault(e.name, e)
                if e.scope == "global":
                    self.globals.add(e.name)
        for lst in self.by_section.values():
            lst.sort(key=lambda t: t[0])
        self.splits = {}  # unit -> {section: (start, end)}
        unit = None
        for l in open(os.path.join(d, "splits.txt")):
            m = re.match(r"^(\S+):\s*$", l)
            if m:
                unit = m.group(1)
                self.splits[unit] = {}
                continue
            m = re.match(r"^\s+(\.\w+)\s+start:0x([0-9A-F]+) end:0x([0-9A-F]+)(.*)$", l)
            if m and unit and " common" not in m.group(4) and m.group(1) not in self.splits[unit]:
                # a unit's common .bss block (REL modules) is a second .bss split; the compiled
                # object's .bss is the first one, commons are SHN_COMMON symbols there
                self.splits[unit][m.group(1)] = (int(m.group(2), 16), int(m.group(3), 16))
        self.refs = {}  # section -> sorted list of relocated-against addresses (filled by collect_refs)
        self.unit_rows = {}  # unit -> number of sym_map rows (strip_unused.py needs at least one per unit)
        for l in self.map_rows[1:]:
            self.unit_rows[l.split("\t")[3]] = self.unit_rows.get(l.split("\t")[3], 0) + 1
        self.changed = 0
        self.log = []
        self.map_rename, self.map_resize, self.map_delete, self.adds = {}, {}, set(), []

    def unit_key(self, stem):
        for u in self.splits:
            if u.rsplit(".", 1)[0] == stem:
                return u
        return None

    def entries(self, section, start, end):
        lst = self.by_section.get(section, [])
        keys = [a for a, _ in lst]
        return [e for _, e in lst[bisect.bisect_left(keys, start):bisect.bisect_left(keys, end)] if self.lines[e.index] is not None]

    def referenced(self, section, start, end):
        """Addresses in [start, end) of `section` some split object relocates against."""
        lst = self.refs.get(section, [])
        return lst[bisect.bisect_left(lst, start):bisect.bisect_left(lst, end)]

    # --- edits (applied by sync_unit after the section's plan validated) ------------------------
    def rename(self, e, new):
        old = e.name
        self.lines[e.index] = new + self.lines[e.index][len(old):]
        self.map_rename[(e.section, e.address)] = new
        e.name = new
        if e.scope == "global":
            self.globals.add(new)
        self.changed += 1
        self.log.append(f"  {old} -> {new}")

    def resize(self, e, size):
        self.lines[e.index] = re.sub(r" size:0x[0-9A-F]+", f" size:0x{size:X}", self.lines[e.index], count=1)
        self.map_resize[(e.section, e.address)] = size
        self.log.append(f"  {e.name}: size {e.size:#x} -> {size:#x}")
        e.size = size
        self.changed += 1

    def delete(self, e, unit):
        self.map_delete.add((e.section, e.address))
        self.lines[e.index] = None
        self.unit_rows[unit] = self.unit_rows.get(unit, 1) - 1
        self.changed += 1
        self.log.append(f"  {e.name} ({e.section}:{e.address:#x} size {e.size:#x}): deleted")

    def add(self, section, address, name, size, scope, unit):
        self.adds.append((section, address, size, unit, scope, name))
        if scope == "global":
            self.globals.add(name)
        self.changed += 1
        self.log.append(f"  {name} ({section}:{address:#x} size {size:#x} {scope}): added")

    def save(self, dry_run):
        if not self.changed:
            return
        # symbols.txt: additions go after the last entry of their section with a lower address
        # (dtk rewrites the file in address order on the next split anyway)
        lines = [l for l in self.lines if l is not None]
        for section, address, size, unit, scope, name in sorted(self.adds, key=lambda t: (t[0], t[1])):
            line = f"{name} = {section}:0x{address:08X}; // type:object size:0x{size:X} scope:{scope}"
            pos = None
            for i, l in enumerate(lines):
                m = SYM_RE.match(l)
                if m and m.group(2) == section and int(m.group(3), 16) < address:
                    pos = i
            if pos is None:
                pos = next((i for i, l in enumerate(lines) if SYM_RE.match(l) and SYM_RE.match(l).group(2) == section), len(lines)) - 1
            lines.insert(pos + 1, line)
        # sym_map.tsv (DOL: address size section unit scope name demangled; module: section offset size ...)
        rows = [self.map_rows[0]]
        for l in self.map_rows[1:]:
            f = l.split("\t")
            key = (f[2], int(f[0], 16)) if self.module is None else (f[0], int(f[1], 16))
            if key in self.map_delete:
                continue
            if key in self.map_rename:
                if f[6] in (".", f[5]) or is_placeholder(f[6]):
                    f[6] = self.map_rename[key]
                f[5] = self.map_rename[key]
            if key in self.map_resize:
                f[1 if self.module is None else 2] = f"0x{self.map_resize[key]:X}"
            rows.append("\t".join(f))
        for section, address, size, unit, scope, name in sorted(self.adds, key=lambda t: (t[0], t[1])):
            if self.module is None:
                row = f"0x{address:08X}\t0x{size:X}\t{section}\t{unit}\t{scope}\t{name}\t{name}"
                pos = max((i for i, r in enumerate(rows) if i and int(r.split("\t")[0], 16) < address), default=0)
            else:
                row = f"{section}\t0x{address:08X}\t0x{size:X}\t{unit}\t{scope}\t{name}\t{name}"
                same = [i for i, r in enumerate(rows) if i and r.split("\t")[0] == section]
                lower = [i for i in same if int(rows[i].split("\t")[1], 16) < address]
                pos = lower[-1] if lower else (same[0] - 1 if same else len(rows) - 1)
            rows.insert(pos + 1, row)
        if dry_run:
            return
        atomic_write(self.path, "\n".join(lines) + "\n")
        atomic_write(self.map_path, "\n".join(rows) + "\n")


def collect_refs(files, targets):
    """Every (section, address) the split objects relocate against, per symbol file: a defined target
    symbol is unit-relative (+ the unit's split start), an undefined one is looked up by name in the
    object's own file, then the DOL's, then every module's."""
    refs = {sf: {} for sf in files.values()}
    order = [files.get(None)] + [sf for m, sf in files.items() if m is not None]
    order = [sf for sf in order if sf is not None]
    for module, unit, path in targets:
        sf = files.get(module)
        if sf is None or unit not in sf.splits:
            continue
        elf = Elf(path)
        for name, sec, value, addend in elf.relocs:
            if sec is not None:
                if sec in sf.splits[unit]:
                    refs[sf].setdefault(sec, set()).add(sf.splits[unit][sec][0] + value + addend)
                continue
            for other in [sf] + order:
                e = other.by_name.get(name)
                if e is not None:
                    refs[other].setdefault(e.section, set()).add(e.address + addend)
                    break
    for sf, d in refs.items():
        sf.refs = {sec: sorted(v) for sec, v in d.items()}


def plan_section(sf, unit, section, start, end, base, tdata, bsize):
    """Edits that make the target symbols of [start, end) agree with the compiled `base`
    ({offset: (size, name, bind)}), or None with a reason when the section must be left alone."""
    entries = sf.entries(section, start, end)
    by_off = {e.address - start: e for e in entries}
    renames, resizes, deletes, adds = [], [], set(), []
    shrink = {}  # target offset -> new size of a placeholder that compiled objects split
    problems, notes = [], []  # problems block the section, notes skip one symbol
    # target symbols with no compiled symbol at their offset
    for off, e in sorted(by_off.items()):
        if off in base:
            continue
        container = [o for o in base if o < off < o + base[o][0]]
        if is_placeholder(e.name) and (section in BSS_SECTIONS or container):
            deletes.add(off)  # padding (.bss) or a fragment of a compiled object
        elif is_placeholder(e.name) and off >= bsize and not any(tdata[off:off + e.size]):
            deletes.add(off)  # zero bytes behind the compiled section's end: the split's alignment padding
        elif off < bsize < off + e.size and not any(tdata[bsize:off + e.size]):
            resizes.append((e, bsize - off))  # the same padding swallowed by the last symbol
        elif container:
            problems.append(f"{e.name} ({section}+{off:#x}) lies inside compiled {base[container[0]][1]}")
        elif section in BSS_SECTIONS:
            problems.append(f"{e.name} ({section}+{off:#x} size {e.size:#x}): no compiled symbol there")
    # compiled symbols
    for off in sorted(base):
        size, name, bind = base[off]
        scope = "global" if bind in (1, 2) else "local"
        e = by_off.get(off)
        if e is None:
            container = [o for o, x in by_off.items() if o < off < o + x.size and o not in deletes]
            if container and container[0] not in base:
                c = by_off[container[0]]
                if not is_placeholder(c.name):
                    problems.append(f"{name} ({section}+{off:#x}) lies inside target {c.name}")
                    continue
                # a placeholder lumping several compiled objects (a pool of statics addressed from
                # one base): it ends where the first compiled object inside it starts
                shrink[container[0]] = min(shrink.get(container[0], c.size), off - container[0])
            if name in sf.globals and scope == "global":
                notes.append(f"  skip {name} ({section}+{off:#x}): already a global of {os.path.relpath(sf.path, ROOT)}")
                continue
            adds.append((off, name, size, scope))
            continue
        if e.size != size:
            resizes.append((e, size))
        if e.name != name and not same_static(e.name, name) and not re.match(r"^@\d+$", name):
            if name in sf.globals:
                notes.append(f"  keep {e.name}: {name} is already a global of {os.path.relpath(sf.path, ROOT)}")
                continue
            renames.append((e, name))
    resizes += [(by_off[o], size) for o, size in shrink.items()]
    if problems:
        return None, problems, notes
    if not (renames or resizes or deletes or adds):
        return None, [], notes

    def layout():
        cov = [(off, x.size) for off, x in by_off.items() if off not in deletes]
        new_size = {e.address - start: sz for e, sz in resizes}
        cov = [(off, new_size.get(off, sz)) for off, sz in cov]
        cov += [(off, size) for off, _, size, _ in adds]
        return sorted(cov)

    def uncovered(cov, lo, hi):
        pos = lo
        for off, sz in cov:
            if off + sz <= lo or off >= hi:
                continue
            if off > pos:
                yield pos, off
            pos = max(pos, off + sz)
        if pos < hi:
            yield pos, hi

    # the rest of a shrunk symbol (a split pool placeholder, a vtable copy whose name is taken):
    # every uncovered range of it that is referenced or holds non-zero bytes gets a placeholder in
    # dtk's format (dtk would otherwise invent one at the first non-zero byte after the relocation
    # pass, which needs the symbol already)
    cov = layout()
    for e, new_size in resizes:
        if new_size >= e.size:
            continue
        o = e.address - start
        for lo, hi in list(uncovered(cov, o, o + e.size)):
            if sf.referenced(section, start + lo, start + hi) or any(tdata[lo:hi]):
                name = f"lbl_{start + lo:08X}" if sf.module is None else f"lbl_{sf.module}_{section[1:]}_{start + lo:X}"
                adds.append((lo, name, hi - lo, "local"))
    # every relocated-against address must stay inside a visible symbol
    covered = layout()
    starts = [o for o, _ in covered]
    lost = []
    for a in sf.referenced(section, start, end):
        i = bisect.bisect_right(starts, a - start) - 1
        if i < 0 or a - start >= covered[i][0] + covered[i][1]:
            lost.append(a)
    if lost:
        return None, [f"relocations against {', '.join(f'{a:#x}' for a in lost[:4])}{'...' if len(lost) > 4 else ''} would lose their symbol"], notes
    return (renames, resizes, sorted(deletes), adds), [], notes


def sync_unit(sf, unit, target, base_obj):
    splits = sf.splits[unit]
    for section in sorted(set(target.sizes) & set(base_obj.sizes) & set(splits)):
        if section not in BSS_SECTIONS and section not in DATA_SECTIONS:
            continue
        if base_obj.sizes[section] > target.sizes[section]:  # the split's section may end with alignment padding
            sf.log.append(f"  {section}: compiled section larger (target {target.sizes[section]:#x}, compiled {base_obj.sizes[section]:#x}); skipped")
            continue
        start, end = splits[section]
        base = base_obj.syms.get(section, {})
        plan, problems, notes = plan_section(sf, unit, section, start, end, base, target.data.get(section, b""), base_obj.sizes[section])
        sf.log.extend(notes)
        if problems:
            sf.log.append(f"  {section} left alone: " + "; ".join(problems))
            continue
        if plan is None:
            continue
        renames, resizes, deletes, adds = plan
        by_off = {e.address - start: e for e in sf.entries(section, start, end)}
        if deletes and not adds and len(deletes) >= sf.unit_rows.get(unit, 0):
            # strip_unused.py treats a unit without any sym_map row as unknown: keep the last one
            sf.log.append(f"  {section}: {', '.join(by_off[o].name for o in deletes)} kept (the unit's last sym_map rows)")
            deletes = []
        for off in deletes:
            sf.delete(by_off[off], unit)
        for e, size in resizes:
            sf.resize(e, size)
        for e, name in renames:
            sf.rename(e, name)
        for off, name, size, scope in adds:
            sf.add(section, start + off, name, size, scope, unit)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    dry_run = "--dry-run" in sys.argv
    quiet = "-q" in sys.argv
    if subprocess.run(["pgrep", "-x", "ninja"], capture_output=True).returncode == 0:
        sys.exit("sync_data_symbols: a ninja build is running; the compiled objects must be complete (post-strip) before they are read")
    cfg = json.load(open(os.path.join(ROOT, "objdiff.json")))
    wanted = {os.path.relpath(os.path.abspath(a), ROOT) for a in args}
    files = {}
    targets = []  # (module, unit, target path) of every split object, for the relocation check
    work = []
    for u in cfg["units"]:
        if "target_path" not in u:
            continue
        tp = os.path.join(ROOT, u["target_path"])
        if not os.path.isfile(tp):
            continue
        rel = os.path.relpath(tp, BUILD).split(os.sep)
        module, stem = (None, "/".join(rel[1:])) if rel[0] == "obj" else (rel[0], "/".join(rel[2:]))
        stem = stem[:-2]
        if module not in files:
            files[module] = SymbolFile(module)
        sf = files[module]
        unit = sf.unit_key(stem)
        if unit is None:
            print(f"{u['name']}: no split unit for {stem} in {os.path.relpath(sf.path, ROOT)}")
            continue
        targets.append((module, unit, tp))
        if not u["metadata"].get("complete"):
            continue  # a unit still being matched: its compiled layout is not the truth yet
        # the compiled object itself, not objdiff.json's base_path (tools/objdiff_base.py's copy of it
        # carries the target's symbols over our anonymous data)
        bp = os.path.join(BUILD, "src", stem + ".o")
        if u.get("base_path") and os.path.isfile(bp) and (not wanted or os.path.relpath(bp, ROOT) in wanted):
            work.append((u["name"], sf, unit, tp, bp))
    collect_refs(files, targets)
    for name, sf, unit, tp, bp in work:
        before = len(sf.log)
        sync_unit(sf, unit, Elf(tp), Elf(bp))
        if len(sf.log) > before and not quiet:
            print(name)
            print("\n".join(sf.log[before:]))
    total = 0
    for sf in files.values():
        sf.save(dry_run)
        total += sf.changed
    print(f"{total} symbol edits{' (dry run, nothing written)' if dry_run else ''}; re-run `python3 configure.py && ninja`")


if __name__ == "__main__":
    main()
