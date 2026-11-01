#!/usr/bin/env python3
"""Match the PS2 debug build's struct fields (orig/ps2/ps2_types.h, stdump output) to the GC
headers' fields and propose renames for the agent-invented placeholders (x103, pad_*, ...).

usage: ps2sym.py                 write build/ps2_rename_plan.tsv, build/ps2_type_candidates.tsv,
                                 build/ps2_enum_candidates.tsv, build/ps2_unmatched.txt
       ps2sym.py --summary       counts per header, unmatched structs on both sides
       ps2sym.py --struct NAME   print one alignment side by side (GC name, or a PS2 name)
       ps2sym.py --params        parameter-name candidates from orig/ps2/ps2_functions.h
                                 -> build/ps2_param_plan.tsv

applying (bytes must not change; the compiler finds the use sites, never a blind sed):
       ps2sym.py --apply include/foo.h [--min-conf 0.8] [--kinds placeholder]
                                 [--only S:f,...] [--skip S:f,...]
                                 rename the declaration lines of that header per the plan; prints
                                 `applied struct old new type conf line` rows (keep them as a map)
       ps2sym.py --fix-errors errors.txt --map map.tsv
                                 rename the use sites the compiler reported (`class X' has no
                                 member named `old', `old' undeclared in a method, no matching
                                 function for call to `X::old'), following #line directives and
                                 macros; one occurrence per pass, so iterate with the build
       ps2sym.py --apply-params [--files a.cpp,b.cpp]
                                 rename placeholder parameters (a, b, c, d, param_N, pN) in
                                 definitions, bodies and prototypes where the PS2 signature agrees
Type names that occur in mangled GC symbols (config/G4BE08/sym_map.tsv, e.g. P10MotionWork) are
the vendor's GC names and must not be renamed to the PS2 typedef names; the link fails if tried.

Fields are matched by SEQUENCE, TYPE and existing-name anchors, never by raw offset: the PS2
layout differs (Vec 16 bytes vs 12, Mtx 0x40 vs 0x30, added/removed fields, packing). Every
struct pair is aligned with a Needleman-Wunsch DP whose pair score combines type compatibility,
name (near-)equality of already-named fields and array dims; the confidence of each pair adds
how well its neighbours align and whether the offset deltas from the previous matched pair agree
once the Vec/Mtx growth is accounted for.
"""
import argparse
import difflib
import subprocess
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PS2_TYPES = ROOT / "orig/ps2/ps2_types.h"
PS2_FUNCS = ROOT / "orig/ps2/ps2_functions.h"
BUILD = ROOT / "build"

PLACEHOLDER = re.compile(r"^(x[0-9A-Fa-f]{1,4}w?|p[0-9A-F]{2,4}|pad[_0-9A-Fa-f]*|field_\w*|unk\w*|dummy\w*)$")
SEMI_PLACEHOLDER = re.compile(r"^[A-Za-z]+[a-z]_?X?([0-9A-F]{2,4})$")

# GC struct name -> PS2 struct name where the vendor renamed the type in the port, or where the
# GC header named an overlay work that the PS2 dump names differently.
ALIASES = {
    "Em10Work": ["FREE_EM10"],
    "MotionWork": ["MOTION_INFO"],
    # the GC cEm header carries the fields of every character overlay (the PS2 split them into
    # the derived classes): align it against the base and those overlays together
    "cEm": ["cEm", "cSubChar", "cPlayer"],
    "EspGenWork": ["cEspgen"],
    "PenCloth": ["CLOTH_INFO"],
    "PlCloth": ["CLOTH_INFO"],
    "PlClothAt": ["CLOTH_AT_SET"],
    "EspInfo": ["cEffectCore"],
}

# ------------------------------------------------------------------ data


class Field:
    __slots__ = ("off", "type", "name", "dims", "line", "file", "group", "path", "comment",
                 "bits", "raw", "nested")

    def __init__(self, off, type_, name, dims, line=0, file="", group=None, path="", comment="",
                 bits=None, raw="", nested=None):
        self.off = off
        self.type = type_
        self.name = name
        self.dims = dims  # list of ints (or None for unknown)
        self.line = line
        self.file = file
        self.group = group  # union group id (fields sharing bytes)
        self.path = path  # nested member path prefix ("stat." for named nested structs)
        self.comment = comment
        self.bits = bits
        self.raw = raw
        self.nested = nested  # Struct for a `struct { ... } name;` member

    @property
    def placeholder(self):
        """x103 / pad_* / unk* names, and prefix+offset names (sub404, flags_324, blendRate500)."""
        if PLACEHOLDER.match(self.name):
            return True
        m = SEMI_PLACEHOLDER.match(self.name)
        if m and self.off is not None:
            suffix = int(m.group(1), 16)
            return suffix == self.off or suffix == (self.off & 0xFFF) or suffix == (self.off & 0xFF)
        return False

    def __repr__(self):
        d = "".join(f"[{x}]" for x in self.dims) if self.dims else ""
        o = f"{self.off:#x}" if self.off is not None else "?"
        return f"{o} {self.type} {self.path}{self.name}{d}"


class Struct:
    def __init__(self, name, kind, file="", line=0):
        self.name = name
        self.kind = kind
        self.file = file
        self.line = line
        self.size = None
        self.bases = []
        self.fields = []
        self.methods = []
        self.nested = []  # named nested aggregates (GC side)
        self.anon = name is None

    def __repr__(self):
        return f"<{self.kind} {self.name} {len(self.fields)} fields {self.file}:{self.line}>"


class Enum:
    def __init__(self, name, file="", line=0):
        self.name = name
        self.members = []
        self.file = file
        self.line = line


# ------------------------------------------------------------------ declarator parsing

FNPTR = re.compile(r"^(.*?)\(\s*(\*+)\s*([A-Za-z_]\w*)\s*((?:\[[^\]]*\])*)\s*\)\s*\((.*)\)$")
DECL = re.compile(r"^(.*?)\s*\b([A-Za-z_]\w*)\s*((?:\[[^\]]*\])*)\s*(?::\s*(\d+))?$")


def eval_dim(expr):
    expr = expr.strip()
    if not expr:
        return None
    if re.fullmatch(r"[0-9a-fA-FxX\s\+\-\*\/\(\)]+", expr):
        try:
            return int(eval(expr, {"__builtins__": {}}, {}))
        except Exception:
            return None
    return None


def parse_declarator(text):
    """'cModel *pParts' -> (type, name, dims, bits). Function pointers get type 'fnptr'."""
    text = text.strip().rstrip(";").strip()
    m = FNPTR.match(text)
    if m:
        dims = [eval_dim(d) for d in re.findall(r"\[([^\]]*)\]", m.group(4))]
        return "fnptr", m.group(3), dims, None
    m = DECL.match(text)
    if not m:
        return None
    type_ = m.group(1).strip()
    name = m.group(2)
    dims = [eval_dim(d) for d in re.findall(r"\[([^\]]*)\]", m.group(3))]
    bits = int(m.group(4)) if m.group(4) else None
    type_ = re.sub(r"\s*\*", "*", type_)
    type_ = re.sub(r"\s+", " ", type_)
    return type_, name, dims, bits


# ------------------------------------------------------------------ PS2 parser

PS2_HEAD = re.compile(r"^(struct|class|union) (\S+)(?: : (.*?))? \{ // 0x([0-9a-f]+)$")
PS2_HEAD_NOSIZE = re.compile(r"^(struct|class|union) (\S+)(?: : (.*?))? \{$")
PS2_TYPEDEF_AGG = re.compile(r"^typedef (struct|union|enum) \{(?: // 0x([0-9a-f]+))?$")
PS2_ENUM = re.compile(r"^enum (\S+) \{$")
PS2_FIELD = re.compile(r"^\t/\* 0x([0-9a-f]+) \*/ (.+);$")
PS2_TYPEDEF = re.compile(r"^typedef (.+?)\s*\b([A-Za-z_]\w*)\s*((?:\[[^\]]*\])*);$")


def parse_ps2(path=PS2_TYPES):
    structs = {}
    enums = {}
    typedefs = {}
    lines = path.read_text(errors="replace").split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        m = PS2_HEAD.match(line) or PS2_HEAD_NOSIZE.match(line)
        tm = PS2_TYPEDEF_AGG.match(line)
        em = PS2_ENUM.match(line)
        if m or tm:
            if m:
                kind, name, bases, size = m.group(1), m.group(2), m.group(3), (m.group(4) if m.lastindex >= 4 else None)
                s = Struct(name, kind, str(path), i + 1)
                if size:
                    s.size = int(size, 16)
                if bases:
                    for b in bases.split(","):
                        b = re.sub(r"/\*.*?\*/", "", b).strip()
                        s.bases.append(b)
            else:
                kind = tm.group(1)
                s = Struct(None, kind, str(path), i + 1)
                if tm.group(2):
                    s.size = int(tm.group(2), 16)
            i += 1
            members = []
            while i < n and not lines[i].startswith("}"):
                fl = lines[i]
                fm = PS2_FIELD.match(fl)
                if fm:
                    d = parse_declarator(fm.group(2))
                    if d:
                        t, nm, dims, bits = d
                        s.fields.append(Field(int(fm.group(1), 16), t, nm, dims, i + 1, str(path), raw=fl.strip()))
                elif kind == "enum" and tm:
                    mm = re.match(r"^\t(\w+) = (-?\d+),?$", fl)
                    if mm:
                        members.append((mm.group(1), int(mm.group(2))))
                elif "(" in fl and not fl.strip().startswith("static "):
                    mm = re.search(r"([~\w]+|operator\S*)\s*\(", fl)
                    if mm:
                        s.methods.append(mm.group(1))
                i += 1
            close = lines[i] if i < n else "}"
            if tm:
                cm = re.match(r"^\} (\S+);$", close)
                s.name = cm.group(1) if cm else f"anon@{s.line}"
            if kind == "enum":
                e = Enum(s.name, str(path), s.line)
                e.members = members
                enums[e.name] = e
            else:
                prev = structs.get(s.name)
                if prev is None or len(s.fields) > len(prev.fields):
                    structs[s.name] = s
            i += 1
            continue
        if em:
            e = Enum(em.group(1), str(path), i + 1)
            i += 1
            while i < n and not lines[i].startswith("}"):
                mm = re.match(r"^\t(\w+) = (-?\d+),?$", lines[i])
                if mm:
                    e.members.append((mm.group(1), int(mm.group(2))))
                i += 1
            enums[e.name] = e
            i += 1
            continue
        tdm = PS2_TYPEDEF.match(line)
        if tdm and "(" not in line:
            typedefs[tdm.group(2)] = (tdm.group(1).strip(), tdm.group(3))
        i += 1
    return structs, enums, typedefs


# ------------------------------------------------------------------ GC parser

AGG_START = re.compile(
    r"^\s*(?:typedef\s+)?(struct|class|union)\s+([A-Za-z_]\w*)?\s*(?::\s*((?:(?:public|private|protected|virtual)\s+)?[\w:<>]+(?:\s*,\s*(?:(?:public|private|protected|virtual)\s+)?[\w:<>]+)*))?\s*\{"
)
OFFSET_COMMENT = re.compile(r"^\s*(?:0x)?([0-9A-Fa-f]{1,5})\b")


def strip_block_comments(text):
    """Remove /* */ comments keeping line structure."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                j = n
            out.append("\n" * text.count("\n", i, j))
            i = j + 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def split_comment(line):
    """Return (code, comment) splitting at // outside strings."""
    in_str = None
    i = 0
    while i < len(line):
        c = line[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "\"'":
            in_str = c
        elif c == "/" and line.startswith("//", i):
            return line[:i], line[i + 2:]
        i += 1
    return line, ""


def scan_balanced(lines, li, ci):
    """From lines[li][ci] (which is '{'), return (li, ci) just after the matching '}'."""
    depth = 0
    in_str = None
    while li < len(lines):
        s = lines[li]
        while ci < len(s):
            c = s[ci]
            if in_str:
                if c == "\\":
                    ci += 2
                    continue
                if c == in_str:
                    in_str = None
            elif c in "\"'":
                in_str = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return li, ci + 1
            ci += 1
        li += 1
        ci = 0
    return li, 0


def parse_gc_file(path, gc_structs, gc_enums, gc_typedefs):
    text = path.read_text(errors="replace")
    text = strip_block_comments(text)
    raw_lines = text.split("\n")
    lines = []
    comments = []
    for l in raw_lines:
        code, com = split_comment(l)
        lines.append(code)
        comments.append(com)
    n = len(lines)
    group_counter = [0]

    def field_comment_offset(com):
        m = OFFSET_COMMENT.match(com)
        if m and re.match(r"^\s*0x", com):
            return int(m.group(1), 16)
        return None

    def parse_body(li, ci, agg):
        """Parse an aggregate body starting after its '{' at lines[li][ci]. Returns (li, ci) after '}'."""
        pending = ""
        pending_line = li
        while li < n:
            s = lines[li][ci:] if ci else lines[li]
            ci = 0
            stripped = s.strip()
            if not stripped:
                li += 1
                continue
            if stripped.startswith("#"):
                li += 1
                continue
            # closing brace of this aggregate
            if stripped.startswith("}"):
                rest = stripped[1:].strip()
                return li, lines[li].index("}") + 1, rest
            if re.match(r"^(public|private|protected)\s*:", stripped):
                li += 1
                continue
            am = AGG_START.match(s)
            if am and "(" not in s[: am.end()]:
                sub = Struct(am.group(2), am.group(1), str(path), li + 1)
                if am.group(3):
                    sub.bases = [re.sub(r"^(public|private|protected|virtual)\s+", "", b.strip()) for b in am.group(3).split(",")]
                bl, bc = li, lines[li].index("{", am.start())
                li2, ci2, rest = parse_body(bl, bc + 1, sub)
                # rest: "name;" / ";" / "name[3];" / "NAME;" for typedef
                rest_code = rest.split(";")[0].strip()
                com = comments[li2]
                if sub.name:
                    gc_structs.setdefault(sub.name, []).append(sub)
                if rest_code and not s.strip().startswith("typedef"):
                    d = parse_declarator(("X " + rest_code))
                    nm, dims = (d[1], d[2]) if d else (rest_code, [])
                    f = Field(field_comment_offset(com), f"struct {sub.name or ''}".strip(), nm, dims, li2 + 1, str(path),
                              comment=com.strip(), nested=sub)
                    if agg is not None:
                        agg.fields.append(f)
                        agg.nested.append(sub)
                elif s.strip().startswith("typedef") and rest_code:
                    sub.name = sub.name or rest_code
                    gc_structs.setdefault(rest_code, []).append(sub)
                elif agg is not None:
                    # anonymous union/struct: flatten members into the parent, sharing a group id for unions
                    if sub.kind == "union":
                        group_counter[0] += 1
                        gid = group_counter[0]
                        for f in sub.fields:
                            if f.group is None:
                                f.group = gid
                            f.path = f.path
                            agg.fields.append(f)
                    else:
                        for f in sub.fields:
                            agg.fields.append(f)
                    agg.nested.extend(sub.nested)
                li = li2 + 1 if ";" in rest or not rest else li2
                if ";" in rest:
                    li = li2 + 1
                    ci = 0
                else:
                    li = li2 + 1
                    ci = 0
                continue
            if re.match(r"^enum\b", stripped):
                if "{" in s:
                    li, ci = scan_balanced(lines, li, lines[li].index("{"))
                    li += 1
                    ci = 0
                else:
                    li += 1
                continue
            if re.match(r"^(template|typedef|friend|using)\b", stripped):
                if "{" in s and ";" not in s.split("{")[0]:
                    li, ci = scan_balanced(lines, li, lines[li].index("{"))
                li += 1
                ci = 0
                continue
            if re.match(r"^static\b", stripped):
                li += 1
                continue
            # method (declaration or inline definition) vs field
            is_fnptr = bool(re.search(r"\(\s*\*+\s*\w+\s*(?:\[[^\]]*\])*\s*\)\s*\(", s))
            if "(" in s and not is_fnptr:
                # accumulate until ';' at depth 0 or a balanced body
                buf = s
                bl = li
                while True:
                    # find first '{' or ';' outside parens
                    depth = 0
                    idx = None
                    for k, c in enumerate(buf):
                        if c == "(":
                            depth += 1
                        elif c == ")":
                            depth -= 1
                        elif c == ";" and depth == 0:
                            idx = ("semi", k)
                            break
                        elif c == "{" and depth == 0:
                            idx = ("brace", k)
                            break
                    if idx:
                        break
                    bl += 1
                    if bl >= n:
                        break
                    buf += "\n" + lines[bl]
                mm = re.search(r"([~\w]+|operator\s*\S+)\s*\(", s)
                if mm:
                    agg.methods.append(mm.group(1))
                if idx and idx[0] == "brace":
                    # position of that brace in lines[bl]
                    off_in_last = idx[1] - (len(buf) - len(lines[bl]))
                    li, ci = scan_balanced(lines, bl, off_in_last)
                    # skip trailing ';' if any
                    li += 1
                    ci = 0
                else:
                    li = bl + 1
                    ci = 0
                continue
            # field declaration(s); may span lines until ';'
            buf = s
            bl = li
            while ";" not in buf and bl + 1 < n and not lines[bl + 1].strip().startswith("}"):
                bl += 1
                buf += " " + lines[bl].strip()
            com = comments[bl].strip() or comments[li].strip()
            off = field_comment_offset(com)
            body = buf.strip().rstrip(";").strip()
            if is_fnptr:
                d = parse_declarator(body)
                if d and agg is not None:
                    agg.fields.append(Field(off, d[0], d[1], d[2], li + 1, str(path), comment=com, raw=buf.strip(), bits=d[3]))
            else:
                # multi-declarator: "f32 x, y, z"
                parts = [p.strip() for p in re.split(r",(?![^\[]*\])", body)]
                d0 = parse_declarator(parts[0])
                if d0 and agg is not None:
                    agg.fields.append(Field(off, d0[0], d0[1], d0[2], li + 1, str(path), comment=com, raw=buf.strip(), bits=d0[3]))
                    base_type = re.sub(r"\*+$", "", d0[0])
                    for p in parts[1:]:
                        d = parse_declarator(base_type + " " + p)
                        if d:
                            agg.fields.append(Field(None, d[0], d[1], d[2], li + 1, str(path), comment=com, raw=buf.strip(), bits=d[3]))
            li = bl + 1
            ci = 0
        return li, 0, ""

    li = 0
    while li < n:
        s = lines[li]
        stripped = s.strip()
        am = AGG_START.match(s)
        if am and not stripped.startswith("//") and "(" not in s[: am.end()] and not re.match(r"^\s*(extern|return)\b", s):
            sub = Struct(am.group(2), am.group(1), str(path), li + 1)
            if am.group(3):
                sub.bases = [re.sub(r"^(public|private|protected|virtual)\s+", "", b.strip()) for b in am.group(3).split(",")]
            bc = lines[li].index("{", am.start())
            li2, ci2, rest = parse_body(li, bc + 1, sub)
            rest_code = rest.split(";")[0].strip()
            if stripped.startswith("typedef") and rest_code:
                nm = re.sub(r"^\*+", "", rest_code.split(",")[0].strip())
                if sub.name and sub.name != nm:
                    gc_typedefs[nm] = sub.name
                sub.name = sub.name or nm
            if sub.name:
                gc_structs.setdefault(sub.name, []).append(sub)
            li = li2 + 1
            continue
        em = re.match(r"^\s*(?:typedef\s+)?enum\s+([A-Za-z_]\w*)?\s*\{", s)
        if em:
            e = Enum(em.group(1), str(path), li + 1)
            li2, ci2 = scan_balanced(lines, li, lines[li].index("{"))
            body = "\n".join(lines[li: li2 + 1])
            body = body[body.index("{") + 1:]
            body = body[: body.rindex("}")]
            val = -1
            for item in body.split(","):
                item = item.strip()
                if not item:
                    continue
                mm = re.match(r"^(\w+)\s*(?:=\s*(.+))?$", item, re.S)
                if mm:
                    if mm.group(2):
                        v = eval_dim(mm.group(2).strip())
                        val = v if v is not None else val + 1
                    else:
                        val += 1
                    e.members.append((mm.group(1), val))
            tail = lines[li2][ci2:].split(";")[0].strip()
            if tail and not e.name:
                e.name = tail
            if e.name:
                gc_enums[e.name] = e
            li = li2 + 1
            continue
        tm = re.match(r"^\s*typedef\s+(.+?)\s*\b([A-Za-z_]\w*)\s*((?:\[[^\]]*\])*)\s*;", s)
        if tm and "(" not in s and "{" not in s:
            gc_typedefs[tm.group(2)] = tm.group(1).strip()
        li += 1


def parse_gc(root=ROOT):
    gc_structs = {}
    gc_enums = {}
    gc_typedefs = {}
    files = sorted((root / "include").rglob("*.h")) + sorted((root / "src").rglob("*.cpp")) + sorted((root / "src").rglob("*.h"))
    for p in files:
        if "dolphin" in p.parts:
            continue
        try:
            parse_gc_file(p, gc_structs, gc_enums, gc_typedefs)
        except Exception as ex:  # a parser bug must be visible, not silent
            print(f"parse error {p}: {ex!r}", file=sys.stderr)
            raise
    return gc_structs, gc_enums, gc_typedefs


# ------------------------------------------------------------------ type canonicalisation

INT_TYPES = {
    "u8": (1, "u"), "uint8": (1, "u"), "unsigned char": (1, "u"), "uchar": (1, "u"), "u_char": (1, "u"),
    "gxbool": (1, "u"), "bool": (1, "u"), "vu8": (1, "u"),
    "s8": (1, "s"), "sint8": (1, "s"), "signed char": (1, "s"), "char": (1, "s"),
    "u16": (2, "u"), "uint16": (2, "u"), "unsigned short": (2, "u"), "short unsigned int": (2, "u"),
    "unsigned short int": (2, "u"), "ushort": (2, "u"), "u_short": (2, "u"), "vu16": (2, "u"), "wchar_t": (2, "u"),
    "s16": (2, "s"), "sint16": (2, "s"), "short": (2, "s"), "short int": (2, "s"), "signed short": (2, "s"),
    "signed short int": (2, "s"), "vs16": (2, "s"),
    "u32": (4, "u"), "uint32": (4, "u"), "unsigned int": (4, "u"), "unsigned long": (4, "u"), "unsigned": (4, "u"),
    "long unsigned int": (4, "u"), "uint": (4, "u"), "u_int": (4, "u"), "u_long": (4, "u"), "size_t": (4, "u"),
    "vu32": (4, "u"), "guid": (4, "u"), "unsigned long int": (4, "u"),
    "s32": (4, "s"), "sint32": (4, "s"), "int": (4, "s"), "long": (4, "s"), "long int": (4, "s"), "signed long": (4, "s"),
    "signed int": (4, "s"), "bool32": (4, "s"), "vs32": (4, "s"), "ptrdiff_t": (4, "s"),
    "u64": (8, "u"), "uint64": (8, "u"), "unsigned long long": (8, "u"), "long long unsigned int": (8, "u"),
    "unsigned long long int": (8, "u"), "s64": (8, "s"), "sint64": (8, "s"), "long long": (8, "s"),
    "long long int": (8, "s"), "signed long long": (8, "s"), "signed long long int": (8, "s"),
}
FLOAT_TYPES = {"f32": 4, "float": 4, "float32": 4, "vf32": 4, "f64": 8, "double": 8, "float64": 8}
# struct spellings that mean the same thing on both sides
STRUCT_SYNONYMS = {
    "tagvec": "vec", "tagvec_": "vec", "point3d": "vec", "vec3": "vec", "scevu0fvector": "vec4", "vec4": "vec4",
    "scevu0fmatrix": "mtx", "mtx44": "mtx", "mtx": "mtx", "mtxptr": "mtx*",
    "_gxcolor": "gxcolor", "gxcolor": "gxcolor", "_gxcolors10": "gxcolors10",
    "s_vec": "svec", "vec2": "vec2", "point2d": "vec2",
}
VEC_LIKE = {"vec"}
SIZES = {}  # normalised struct name -> {"gc": size, "ps2": size}; filled by the driver
MTX_LIKE = {"mtx"}


def norm_struct_name(name):
    n = name.strip()
    n = re.sub(r"^(struct|class|union|enum)\s+", "", n)
    n = n.replace(" ", "")
    low = n.lower()
    if low in STRUCT_SYNONYMS:
        return STRUCT_SYNONYMS[low]
    low = re.sub(r"^tag", "", low)
    low = re.sub(r"^_+", "", low)
    low = re.sub(r"_(t|tag|s)$", "", low)
    # the PS2 dump names the per-unit work overlays FREE_EMXX / FREE_OBJXX; ours are EmXXWork
    if low.startswith("free_"):
        low = low[5:] + "work"
    low = low.replace("_", "")
    low = re.sub(r"wk$", "work", low)
    return low


class TypeCanon:
    def __init__(self, ps2_typedefs, ps2_structs, ps2_enums, gc_typedefs, gc_structs, gc_enums):
        self.ps2_typedefs = ps2_typedefs
        self.ps2_structs = ps2_structs
        self.ps2_enums = ps2_enums
        self.gc_typedefs = gc_typedefs
        self.gc_structs = gc_structs
        self.gc_enums = gc_enums
        self.sizes = SIZES
        self._gc_size_cache = {}

    def gc_struct_size(self, name):
        """Byte size of a GC aggregate from its last field's offset + size (None when unknown)."""
        if name in self._gc_size_cache:
            return self._gc_size_cache[name]
        self._gc_size_cache[name] = None
        best = None
        for s in self.gc_structs.get(name, []):
            end = None
            for f in flatten(s):
                if f.off is None:
                    continue
                sz = struct_size(self.canon(f.type, "gc"), "gc", self)
                if sz is None:
                    sz = 4  # unknown aggregate: at least a word; the size is a lower bound then
                if f.bits is not None:
                    sz = 4
                e = f.off + sz
                end = e if end is None else max(end, e)
            if end is not None:
                # classes with a vptr / alignment: round to 4
                end = (end + 3) & ~3
                best = end if best is None else max(best, end)
        self._gc_size_cache[name] = best
        return best

    def resolve(self, t, side):
        """Follow typedef chains; return (base_type_str, extra_pointer_depth, extra_dims)."""
        t = t.strip()
        ptr = 0
        dims = []
        for _ in range(12):
            while t.endswith("*"):
                ptr += 1
                t = t[:-1].strip()
            t = re.sub(r"^(const|volatile|static)\s+", "", t)
            t = re.sub(r"\s+(const|volatile)$", "", t)
            low = t.lower()
            if low in INT_TYPES or low in FLOAT_TYPES or t == "fnptr" or t == "void":
                break
            nm = re.sub(r"^(struct|class|union|enum)\s+", "", t)
            if side == "ps2":
                if nm in self.ps2_structs or nm in self.ps2_enums:
                    break
                td = self.ps2_typedefs.get(nm)
                if td is None:
                    break
                base, d = td
                if d:
                    dims += [eval_dim(x) for x in re.findall(r"\[([^\]]*)\]", d)]
                if base.startswith("struct") or base.startswith("union") or base.startswith("enum"):
                    if norm_struct_name(base) == norm_struct_name(nm):
                        break
                t = base
            else:
                if nm in self.gc_structs or nm in self.gc_enums:
                    break
                td = self.gc_typedefs.get(nm)
                if td is None:
                    break
                if "[" in td:
                    dims += [eval_dim(x) for x in re.findall(r"\[([^\]]*)\]", td)]
                    td = td[: td.index("[")]
                if td.strip() == nm:
                    break
                t = td
        return t, ptr, dims

    def canon(self, type_str, side):
        """-> (kind, detail) kind in i,f,p,S,e,fp,v(oid)"""
        if type_str == "fnptr":
            return ("fp", "")
        raw = re.sub(r"^(const|volatile)\s+", "", type_str.strip())
        raw = re.sub(r"^(struct|class|union)\s+", "", raw)
        if raw.lower() in STRUCT_SYNONYMS and not raw.endswith("*"):
            syn = STRUCT_SYNONYMS[raw.lower()]
            if syn.endswith("*"):
                return ("p", (1, ("S", syn[:-1])))
            return ("S", syn)
        base, ptr, dims = self.resolve(type_str, side)
        low = base.lower()
        if ptr:
            inner = self.canon(base, side) if base != "void" else ("v", "")
            return ("p", (ptr, inner))
        if low in INT_TYPES:
            c = ("i", INT_TYPES[low])
        elif low in FLOAT_TYPES:
            c = ("f", FLOAT_TYPES[low])
        elif low == "void":
            c = ("v", "")
        else:
            nm = re.sub(r"^(struct|class|union|enum)\s+", "", base)
            if (side == "ps2" and nm in self.ps2_enums) or (side == "gc" and nm in self.gc_enums):
                c = ("e", nm)
            else:
                nn = norm_struct_name(nm)
                if nn.endswith("*"):
                    return ("p", (1, ("S", nn[:-1])))
                c = ("S", nn)
        if dims:
            c = ("a", (c, dims))
        return c


def struct_size(canon, side, tc):
    """Best-effort byte size of a canonical type on `side` (None when unknown)."""
    k, d = canon
    if k == "i":
        return d[0]
    if k == "f":
        return d
    if k in ("p", "fp"):
        return 4
    if k == "S":
        if d in VEC_LIKE:
            return 16 if side == "ps2" else 12
        if d in MTX_LIKE:
            return 0x40 if side == "ps2" else 0x30
        if d == "vec4":
            return 16
        if d == "gxcolor":
            return 4
        return tc.sizes.get(d, {}).get(side)
    if k == "a":
        inner = struct_size(d[0], side, tc)
        if inner is None:
            return None
        for x in d[1]:
            if x is None:
                return None
            inner *= x
        return inner
    return None


def type_score(gc, ps2):
    """0..1 compatibility of canonical types (gc from the GC header, ps2 from the dump)."""
    gk, gd = gc
    pk, pd = ps2
    if gk == "a" or pk == "a":
        if gk == "a" and pk == "a":
            s = type_score(gd[0], pd[0])
            return s * (1.0 if gd[1] == pd[1] else 0.6)
        if gk == "a":
            # GC array vs PS2 scalar: a byte pad array vs anything is weak
            return type_score(gd[0], ps2) * 0.35
        return type_score(gc, pd[0]) * 0.35
    if gk == "i" and pk == "i":
        if gd == pd:
            return 1.0
        if gd[0] == pd[0]:
            return 0.85
        return 0.12
    if gk == "f" and pk == "f":
        return 1.0 if gd == pd else 0.2
    if gk == "e":
        gk, gd = "i", (4, "s")
    if pk == "e":
        if gk == "i":
            return 0.78
        return 0.08
    if gk == "i" and pk == "f" or gk == "f" and pk == "i":
        gs = gd[0] if gk == "i" else gd
        ps = pd[0] if pk == "i" else pd
        return 0.3 if gs == ps else 0.05
    if gk == "p" and pk == "p":
        gi, pi = gd[1], pd[1]
        if gd[0] != pd[0]:
            return 0.5
        if gi[0] == "v" or pi[0] == "v":
            return 0.8
        if gi == pi:
            return 1.0
        if gi[0] == "S" and pi[0] == "S":
            return 0.55
        if gi[0] == pi[0]:
            return 0.6 if gi[0] != "i" else (0.85 if gi[1][0] == pi[1][0] else 0.5)
        return 0.35
    if gk == "fp" and pk == "fp":
        return 1.0
    if gk == "fp" and pk == "p" or gk == "p" and pk == "fp":
        return 0.6
    if (gk == "p" or gk == "fp") and pk == "i":
        return 0.55 if pd[0] == 4 else 0.05
    if gk == "i" and (pk == "p" or pk == "fp"):
        return 0.55 if gd[0] == 4 else 0.05
    if gk == "S" and pk == "S":
        if gd == pd:
            return 1.0
        gs = SIZES.get(gd, {}).get("gc")
        ps = SIZES.get(pd, {}).get("ps2")
        if gs is not None and ps is not None and (gs == ps or gs + 4 == ps or gs + 8 == ps or gs + 12 == ps):
            return 0.6  # same-sized aggregate under another name: a type the port renamed
        return 0.15
    if gk == "S" or pk == "S":
        return 0.05
    return 0.05


# ------------------------------------------------------------------ name similarity

SYNONYMS = {
    "nrm": "norm", "normal": "norm", "position": "pos", "rotation": "rot", "cnt": "count", "counter": "count",
    "num": "no", "number": "no", "idx": "index", "tbl": "table", "mdl": "model", "ptr": "p", "prev": "old",
    "previous": "old", "spd": "speed", "sca": "scale", "ang": "rot", "angle": "rot", "mat": "matrix",
    "mtx": "matrix", "info": "info", "flg": "flag", "flags": "flag", "wk": "work", "sub": "sub",
    "col": "color", "colour": "color", "rgb": "color", "tex": "texture", "id": "id", "seid": "seid",
    "mot": "motion", "mtn": "motion", "atr": "atari", "atari": "atari", "ck": "check", "chk": "check",
    "req": "request", "dist": "distance", "dir": "dir", "len": "length", "max": "max", "min": "min",
    "vec": "vector", "sec": "second", "frm": "frame", "hgt": "height", "h": "height", "w": "width",
    "wid": "width", "rad": "radius", "r": "radius", "fsd": "footshadow", "shd": "shadow", "shdw": "shadow",
    "pl": "player", "em": "enemy", "eff": "effect", "efc": "effect", "se": "se", "snd": "sound",
    "oba": "oba", "sca_": "sca", "lit": "light", "lgt": "light", "no_": "no", "rno": "rno",
}


def tokens(name):
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    toks = [t.lower() for t in re.split(r"[_\s]+", s) if t]
    out = []
    for t in toks:
        # split trailing digits: pos2 -> pos, 2
        m = re.match(r"^([a-z]+)(\d+)$", t)
        if m:
            out.append(SYNONYMS.get(m.group(1), m.group(1)))
            out.append(m.group(2))
        else:
            out.append(SYNONYMS.get(t, t))
    # leading hungarian p for pointers: pParts -> p, parts
    return out


def name_score(gc_name, ps2_name, gc_placeholder=None):
    """1.0 exact, 0.9 same tokens, ... ; -0.15 clearly different; None when gc is a placeholder."""
    if gc_placeholder if gc_placeholder is not None else PLACEHOLDER.match(gc_name):
        return None
    a = gc_name.lower().replace("_", "")
    b = ps2_name.lower().replace("_", "")
    if a == b:
        return 1.0
    ta = tokens(gc_name)
    tb = tokens(ps2_name)
    if ta == tb or (set(ta) == set(tb) and len(ta) == len(tb)):
        return 0.9
    if set(ta) == set(tb):
        return 0.85
    # hungarian / member prefixes: m_, p
    ta2 = [t for t in ta if t not in ("m", "p")]
    tb2 = [t for t in tb if t not in ("m", "p")]
    if ta2 and ta2 == tb2:
        return 0.85
    common = set(ta2) & set(tb2)
    if common and len(common) >= max(1, min(len(ta2), len(tb2)) * 0.5) and len(common) >= 1:
        # avoid matching on trivial shared tokens alone
        trivial = {"no", "flag", "count", "p", "m", "type", "0", "1", "2", "3", "old", "pos"}
        if common - trivial or len(common) >= 2:
            return 0.6
    r = difflib.SequenceMatcher(None, a, b).ratio()
    if r >= 0.8:
        return 0.6
    if r >= 0.65:
        return 0.3
    if "".join(ta2) and "".join(tb2) and ("".join(ta2) in "".join(tb2) or "".join(tb2) in "".join(ta2)):
        return 0.4
    return -0.15


# ------------------------------------------------------------------ struct pairing


def pair_structs(gc_structs, ps2_structs):
    """-> list of (gc_name, ps2_name, how), unmatched_gc, unmatched_ps2"""
    ps2_by_norm = defaultdict(list)
    for nm in ps2_structs:
        ps2_by_norm[norm_struct_name(nm)].append(nm)
    pairs = []
    used_ps2 = set()
    unmatched_gc = []
    for gname in gc_structs:
        cand = None
        how = "name"
        if gname in ALIASES and all(a in ps2_structs for a in ALIASES[gname]):
            cand = "+".join(ALIASES[gname])
            how = "alias"
        elif gname in ps2_structs:
            cand = gname
        else:
            nn = norm_struct_name(gname)
            lst = ps2_by_norm.get(nn)
            if lst:
                cand = lst[0]
                how = "name~"
        if cand is None:
            unmatched_gc.append(gname)
            continue
        pairs.append((gname, cand, how))
        used_ps2.add(cand)
    # content pairing for GC structs with no name match: field-name overlap
    gc_left = []
    for gname in unmatched_gc:
        best = None
        gnames = set()
        for s in gc_structs[gname]:
            gnames |= {f.name.lower() for f in s.fields if not f.placeholder}
        if len(gnames) < 3:
            gc_left.append(gname)
            continue
        for pname, ps in ps2_structs.items():
            if pname in used_ps2:
                continue
            pn = {f.name.lower() for f in ps.fields}
            if not pn:
                continue
            common = len(gnames & pn)
            j = common / len(gnames | pn)
            if common >= 3 and j >= 0.3 and (best is None or j > best[0]):
                best = (j, pname)
        if best:
            pairs.append((gname, best[1], f"content j={best[0]:.2f}"))
            used_ps2.add(best[1])
        else:
            gc_left.append(gname)
    unmatched_ps2 = [n for n in ps2_structs if n not in used_ps2]
    return pairs, gc_left, unmatched_ps2


# ------------------------------------------------------------------ alignment

GAP = -0.35


def align(gfields, pfields, tc, gsize=None, psize=None):
    """Needleman-Wunsch over the two field sequences. Returns list of (gi, pj) matches."""
    G = [tc.canon(f.type, "gc") for f in gfields]
    P = [tc.canon(f.type, "ps2") for f in pfields]
    n, m = len(gfields), len(pfields)
    if n == 0 or m == 0:
        return [], G, P, set()
    # relative position prior: (off - first)/(size - first) on both sides; only a soft term
    gstart = min((f.off for f in gfields if f.off is not None), default=None)
    pstart = min((f.off for f in pfields if f.off is not None), default=None)
    use_pos = gsize and psize and gstart is not None and pstart is not None and gsize > gstart and psize > pstart
    if use_pos:
        ratio = (gsize - gstart) / float(psize - pstart)
        use_pos = 0.6 <= ratio <= 1.4  # an overlay union of every derived work is no layout prior

    def relpos(f, start, size):
        return None if f.off is None else (f.off - start) / float(size - start)

    S = [[0.0] * m for _ in range(n)]
    for i in range(n):
        gf = gfields[i]
        rg = relpos(gf, gstart, gsize) if use_pos else None
        for j in range(m):
            pf = pfields[j]
            ts = type_score(G[i], P[j])
            ns = name_score(gf.name, pf.name, gf.placeholder)
            s = 2.0 * ts - 1.0
            if rg is not None:
                rp = relpos(pf, pstart, psize)
                if rp is not None:
                    dev = abs(rg - rp)
                    if dev > 0.12:
                        s -= 3.0 * (dev - 0.12)
            if ns is not None:
                if ns >= 0.85:
                    s += 2.0 * ns
                elif ns >= 0.55:
                    s += 1.2 * ns
                elif ns > 0:
                    s += 0.5 * ns
                else:
                    s += ns
            # pads (byte arrays) are weak evidence; keep them from grabbing real fields
            if gf.placeholder and gf.name.startswith("pad"):
                s -= 0.6
            if gf.bits is not None:
                s -= 0.4
            S[i][j] = s
    # skipping a GC field that aliases another one's bytes (union member, or same offset as its
    # predecessor) costs almost nothing: only one alias can carry the vendor name
    ggap = []
    for i, f in enumerate(gfields):
        cheap = f.group is not None
        if not cheap and i > 0 and f.off is not None and gfields[i - 1].off == f.off:
            cheap = True
        if not cheap and i + 1 < n and f.off is not None and gfields[i + 1].off == f.off:
            cheap = True
        ggap.append(-0.05 if cheap else GAP)
    NEG = float("-inf")
    D = [[NEG] * (m + 1) for _ in range(n + 1)]
    T = [[0] * (m + 1) for _ in range(n + 1)]
    D[0][0] = 0.0
    for i in range(1, n + 1):
        D[i][0] = D[i - 1][0] + ggap[i - 1]
        T[i][0] = 1
    for j in range(1, m + 1):
        D[0][j] = D[0][j - 1] + GAP
        T[0][j] = 2
    for i in range(1, n + 1):
        Di = D[i]
        Dp = D[i - 1]
        Si = S[i - 1]
        Ti = T[i]
        gi_gap = ggap[i - 1]
        for j in range(1, m + 1):
            a = Dp[j - 1] + Si[j - 1]
            b = Dp[j] + gi_gap
            c = Di[j - 1] + GAP
            if a >= b and a >= c:
                Di[j] = a
                Ti[j] = 0
            elif b >= c:
                Di[j] = b
                Ti[j] = 1
            else:
                Di[j] = c
                Ti[j] = 2
    i, j = n, m
    matches = []
    while i > 0 or j > 0:
        t = T[i][j]
        if t == 0:
            if S[i - 1][j - 1] > 0.0:
                matches.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif t == 1:
            i -= 1
        else:
            j -= 1
    matches.reverse()
    # post pass: fields moved in the port (cCoord::pParent) still pair when names are equal
    mg = {a for a, _ in matches}
    mp = {b for _, b in matches}
    moved = set()
    cands = []
    for i2, gf in enumerate(gfields):
        if i2 in mg or gf.placeholder:
            continue
        for j2, pf in enumerate(pfields):
            if j2 in mp:
                continue
            ns = name_score(gf.name, pf.name, gf.placeholder)
            if ns is not None and ns >= 0.85:
                ts = type_score(G[i2], P[j2])
                if ts >= 0.5:
                    cands.append((ns, ts, i2, j2))
    cands.sort(key=lambda c: (-c[0], -c[1]))
    anchors = []
    for ns, ts, i2, j2 in cands:
        if i2 in mg or j2 in mp:
            continue
        moved.add((i2, j2))
        anchors.append((i2, j2))
        mg.add(i2)
        mp.add(j2)
    # a moved anchor drags its block along: neighbours on both sides with the same type and the
    # same offset delta (Vec/Mtx growth accounted for) belong to the same relocated block
    for i2, j2 in anchors:
        for step in (1, -1):
            a, b = i2, j2
            while True:
                a2, b2 = a + step, b + step
                if not (0 <= a2 < len(gfields) and 0 <= b2 < len(pfields)) or a2 in mg or b2 in mp:
                    break
                ga, pb = gfields[a2], pfields[b2]
                if ga.off is None or pb.off is None or type_score(G[a2], P[b2]) < 0.85:
                    break
                lo, hi = (a, a2) if step > 0 else (a2, a)
                dg = gfields[hi].off - gfields[lo].off
                dp = (pfields[b2].off - pfields[b].off) * step
                grow = vec_growth(G[lo], tc)
                if dp != dg + grow and not (0 < dp - dg - grow < 16 and is_aggregate(P[b2] if step > 0 else P[b])):
                    break
                moved.add((a2, b2))
                mg.add(a2)
                mp.add(b2)
                a, b = a2, b2
    return matches, G, P, moved


def vec_growth(canon, tc):
    """Bytes a GC field grows by on the PS2 (Vec 12->16, Mtx 0x30->0x40)."""
    k, d = canon
    if k == "a":
        inner = vec_growth(d[0], tc)
        for x in d[1]:
            if x is None:
                return 0
            inner *= x
        return inner
    if k == "S":
        if d in VEC_LIKE:
            return 4
        if d in MTX_LIKE:
            return 0x10
        sz = tc.sizes.get(d)
        if sz and sz.get("gc") is not None and sz.get("ps2") is not None:
            return sz["ps2"] - sz["gc"]
    return 0


def is_aggregate(canon):
    return canon[0] == "S" or (canon[0] == "a" and canon[1][0][0] == "S")


def growth_between(gfields, G, tc, a, b, matched):
    """Bytes the GC fields [a, b) grow by on the PS2; aliases of one offset count once (the alias
    that carries a match decides, otherwise the smallest growth: 3 floats over a Vec stay 0)."""
    g0 = gfields[a].off
    gb = gfields[b].off
    by_off = {}
    nalign = 0
    for x in range(a, b):
        fx = gfields[x]
        if fx.off is None or not (g0 <= fx.off < gb):
            continue
        g = vec_growth(G[x], tc)
        if x in matched:
            by_off[fx.off] = (1, g)
        elif fx.off not in by_off:
            by_off[fx.off] = (0, g)
        elif by_off[fx.off][0] == 0:
            by_off[fx.off] = (0, min(by_off[fx.off][1], g))
        if is_aggregate(G[x]):
            nalign += 1
    return sum(v for _, v in by_off.values()), nalign


def confidence(matches, gfields, pfields, G, P, tc, moved=()):
    """-> dict (gi,pj) -> (conf, flags); `matches` is the monotone DP alignment, `moved` the
    name-anchored pairs outside it (fields the port reordered)."""
    out = {}
    for gi, pj in moved:
        ts = type_score(G[gi], P[pj])
        ns = name_score(gfields[gi].name, pfields[pj].name, gfields[gi].placeholder)
        if ns is not None and ns >= 0.85:
            out[(gi, pj)] = (round(0.9 if ts >= 0.85 else 0.7, 2), ["name", "moved"])
        else:
            out[(gi, pj)] = (round(0.85 if ts >= 0.85 else 0.6, 2), ["moved-block"] + (["name!"] if ns is not None and ns < 0 else []))
    matched_gi = {a for a, _ in matches}
    n = len(matches)
    # pass 1: local offset consistency with the previous match (or the struct start)
    local = [None] * n  # True / False / None(unknown or mild)
    ldiff = [0] * n
    for k, (gi, pj) in enumerate(matches):
        gf, pf = gfields[gi], pfields[pj]
        if gf.off is None or pf.off is None:
            continue
        pg, pp = matches[k - 1] if k > 0 else (0, 0)
        g0, p0 = gfields[pg], pfields[pp]
        if g0.off is None or p0.off is None or g0.off > gf.off or p0.off > pf.off:
            continue
        adj, _ = growth_between(gfields, G, tc, pg, gi, matched_gi)
        diff = (pf.off - p0.off) - (gf.off - g0.off) - adj
        ldiff[k] = diff
        psz = struct_size(P[pj], "ps2", tc)
        if diff == 0:
            local[k] = True
        elif 0 < diff < 16 and (P[pj][0] == "S" or (psz and psz >= 8)):
            local[k] = "pad"
        elif abs(diff) <= 4 and (pf.off - p0.off) != 0:
            local[k] = None
        else:
            local[k] = False
    # a match whose PS2 field belongs to another overlay struct than the previous match's
    # (composite targets) has no offset relation to it
    for k in range(1, n):
        if pfields[matches[k][1]].path != pfields[matches[k - 1][1]].path:
            local[k] = False if local[k] is None else local[k]
    # runs of adjacent, locally consistent matches (a block the port moved as a whole)
    run_len = [1] * n
    run_id = [0] * n
    k = 0
    while k < n:
        j = k
        while j + 1 < n and matches[j + 1] == (matches[j][0] + 1, matches[j][1] + 1) and local[j + 1] in (True, "pad"):
            j += 1
        for x in range(k, j + 1):
            run_len[x] = j - k + 1
            run_id[x] = k
        k = j + 1
    # a run is trustworthy when a name anchors it or its type pattern is not one repeated type
    run_ok = {}
    for k in range(n):
        rid = run_id[k]
        if rid in run_ok:
            continue
        members = [x for x in range(n) if run_id[x] == rid]
        anchored = False
        types = set()
        for x in members:
            gi, pj = matches[x]
            ns = name_score(gfields[gi].name, pfields[pj].name, gfields[gi].placeholder)
            if ns is not None and ns >= 0.55:
                anchored = True
            types.add(P[pj])
        run_ok[rid] = anchored or len(types) >= 2 or len(members) >= 6 or matches[members[0]] == (0, 0)
    # pass 2
    names = {}
    for k, (gi, pj) in enumerate(matches):
        gf, pf = gfields[gi], pfields[pj]
        ts = type_score(G[gi], P[pj])
        ns = name_score(gf.name, pf.name, gf.placeholder)
        names[k] = ns
        flags = []
        prev_ok = (k > 0 and matches[k - 1] == (gi - 1, pj - 1)) or (gi == 0 and pj == 0)
        next_ok = (k + 1 < n and matches[k + 1] == (gi + 1, pj + 1)) or (gi == len(gfields) - 1 and pj == len(pfields) - 1)
        if not prev_ok and k > 0:
            pg, pp = matches[k - 1]
            if pp == pj - 1:
                between = gfields[pg + 1: gi]
                if between and all(b.off is not None and gfields[pg].off is not None and b.off < gfields[pg].off + 16 for b in between):
                    prev_ok = True  # only aliases of the previous match's bytes lie between
        if not next_ok and k + 1 < n:
            ng, np_ = matches[k + 1]
            if np_ == pj + 1 and gf.group is not None:
                between = gfields[gi + 1: ng]
                if between and all(b.group == gf.group for b in between):
                    next_ok = True
        ctx = (0.5 if prev_ok else 0.0) + (0.5 if next_ok else 0.0)
        offs = local[k]
        if offs == "pad":
            flags.append("pad")
            offs = True
        elif offs is None and ldiff[k]:
            flags.append(f"off{ldiff[k]:+d}")
        elif offs is False:
            flags.append(f"off{ldiff[k]:+d}")
        # drift since the last name-anchored match (or the struct start): an insertion in the
        # port shifts everything after it; local consistency alone would hide that
        drift = 0
        if gf.off is not None and pf.off is not None:
            ak = None
            for kk in range(k - 1, -1, -1):
                if names.get(kk) is not None and names[kk] >= 0.55:
                    ak = kk
                    break
            ag, ap = matches[ak] if ak is not None else (0, 0)
            g0, p0 = gfields[ag], pfields[ap]
            if g0.off is not None and p0.off is not None and g0.off <= gf.off and p0.off <= pf.off:
                adj, nalign = growth_between(gfields, G, tc, ag, gi, matched_gi)
                if is_aggregate(P[pj]):
                    nalign += 1
                d = (pf.off - p0.off) - (gf.off - g0.off) - adj
                if not (d == 0 or (0 < d <= 12 * nalign)):
                    drift = d
        conf = 0.5 * ts + 0.3 * ctx + (0.2 if offs else (0.1 if offs is None else 0.0))
        if drift:
            if run_len[k] >= 5:
                flags.append("block")
            else:
                conf -= 0.25
                flags.append(f"drift{drift:+d}")
        if ns is not None:
            if ns >= 0.85:
                conf = max(conf, 0.9)
                flags.append("name")
            elif ns >= 0.55:
                conf = max(conf, 0.75)
                flags.append("name~")
            elif ns < 0:
                conf -= 0.15
                flags.append("name!")
        if offs is False:
            conf -= 0.15
            if abs(ldiff[k]) > 16:
                conf = min(conf, 0.45 if ns is None else 0.6)
        if gf.placeholder and gf.name.startswith("pad"):
            conf -= 0.3
            flags.append("padfield")
        if not run_ok[run_id[k]] and (ns is None or ns < 0.55) and conf > 0.75:
            conf = 0.75
            flags.append("chain")
        out[(gi, pj)] = (round(max(0.0, min(1.0, conf)), 2), flags)
    # struct-level layout agreement: when most matched pairs disagree on their offset deltas the
    # port reorganised the struct and sequence evidence alone is not enough for a rename
    incons = sum(1 for k in range(n) if local[k] is False)
    if n >= 4 and incons / n > 0.4:
        for k in range(n):
            conf, flags = out[matches[k]]
            if "name" not in flags and "name~" not in flags and conf > 0.7 and run_len[k] < 5:
                out[matches[k]] = (0.7, flags + ["reorg"])
    return out


def flatten(struct):
    """GC struct fields ordered by offset (declaration order where the offset is unknown), expanding
    named nested anonymous aggregates. Union branches thereby interleave by offset, so the aligner
    sees every alias of the same bytes next to each other and skips the losers for free."""
    out = []
    for f in struct.fields:
        if f.nested is not None and not f.nested.name:
            for sub in flatten(f.nested):
                sub2 = Field(sub.off, sub.type, sub.name, sub.dims, sub.line, sub.file, sub.group,
                             f.name + "." + sub.path, sub.comment, sub.bits, sub.raw, sub.nested)
                out.append(sub2)
        else:
            out.append(f)
    eff = []
    last = -1.0
    for k, f in enumerate(out):
        if f.off is not None:
            last = float(f.off)
        else:
            last += 1e-3
        eff.append((last, k))
    order = sorted(range(len(out)), key=lambda k: eff[k])
    return [out[k] for k in order]


# ------------------------------------------------------------------ driver


def fmt_field(f):
    d = "".join(f"[{x if x is not None else '?'}]" for x in f.dims) if f.dims else ""
    o = f"{f.off:#05x}" if f.off is not None else "  ?  "
    return f"{o} {f.type} {f.path}{f.name}{d}"


def run(args):
    ps2_structs, ps2_enums, ps2_typedefs = parse_ps2()
    gc_structs, gc_enums, gc_typedefs = parse_gc()
    tc = TypeCanon(ps2_typedefs, ps2_structs, ps2_enums, gc_typedefs, gc_structs, gc_enums)
    pairs, un_gc, un_ps2 = pair_structs(gc_structs, ps2_structs)
    for pname, ps in ps2_structs.items():
        if ps.size is not None:
            tc.sizes.setdefault(norm_struct_name(pname), {})["ps2"] = ps.size
    for gname, pname, how in pairs:
        gs = tc.gc_struct_size(gname)
        if gs is not None:
            tc.sizes.setdefault(norm_struct_name(gname), {})["gc"] = gs
            if "+" not in pname and norm_struct_name(gname) != norm_struct_name(pname):
                tc.sizes.setdefault(norm_struct_name(pname), {})["gc"] = gs

    plan = []  # rows
    type_cands = []
    per_header = defaultdict(lambda: [0, 0, 0])  # placeholders, high renames, named renames
    alignments = {}

    for gname, pname, how in pairs:
        if "+" in pname:
            parts = [ps2_structs[x] for x in pname.split("+")]
            ps = Struct(pname, "struct", parts[0].file, parts[0].line)
            ps.size = max(x.size or 0 for x in parts)
            for x in parts:
                for f in x.fields:
                    f2 = Field(f.off, f.type, f.name, f.dims, f.line, f.file, raw=f.raw)
                    f2.path = x.name + "::"
                    ps.fields.append(f2)
        else:
            ps = ps2_structs[pname]
        for gs in gc_structs[gname]:
            gfields = flatten(gs)
            pfields = ps.fields
            matches, G, P, moved = align(gfields, pfields, tc, tc.gc_struct_size(gname), ps.size)
            confs = confidence(matches, gfields, pfields, G, P, tc, moved)
            matches = sorted(matches + list(moved))
            alignments.setdefault(gname, []).append((gs, ps, gfields, pfields, matches, confs, how, G, P, moved))
            hdr = os.path.relpath(gs.file, ROOT)
            for f in gfields:
                if f.placeholder and not f.name.startswith("pad"):
                    per_header[hdr][0] += 1
            matched_g = {gi for gi, _ in matches}
            for (gi, pj), (conf, flags) in confs.items():
                gf, pf = gfields[gi], pfields[pj]
                same = gf.name == pf.name
                if same:
                    kind = "same"
                elif gf.placeholder:
                    kind = "pad" if gf.name.startswith("pad") else "placeholder"
                elif "name" in flags or "name~" in flags:
                    kind = "named~"  # near-equal names: cosmetic vendor spelling
                else:
                    kind = "named"
                ptype = pf.type + ("".join(f"[{x}]" for x in pf.dims) if pf.dims else "")
                gtype = gf.type + ("".join(f"[{x}]" for x in gf.dims) if gf.dims else "")
                plan.append((gname, gf.path + gf.name, pf.name, ptype, gtype, f"{conf:.2f}", kind,
                             f"{hdr}:{gf.line}", ",".join(flags), pf.path.rstrip(":") or pname))
                if kind == "placeholder" and conf >= 0.8:
                    per_header[hdr][1] += 1
                if kind.startswith("named") and conf >= 0.8:
                    per_header[hdr][2] += 1
                # type-name candidates: struct-typed pairs whose GC type has no PS2 struct of that name
                gk = G[gi]
                pk = P[pj]
                if gk[0] == "a":
                    gk = gk[1][0]
                if pk[0] == "a":
                    pk = pk[1][0]
                if gk[0] == "S" and pk[0] == "S" and gk[1] != pk[1]:
                    gbase = tc.resolve(gf.type, "gc")[0]
                    pbase = tc.resolve(pf.type, "ps2")[0]
                    if norm_struct_name(gbase) not in {norm_struct_name(x) for x in ps2_structs}:
                        type_cands.append((gname, gf.path + gf.name, gbase, pbase, f"{conf:.2f}", f"{hdr}:{gf.line}",
                                           "anon-nested" if gf.nested is not None else "typedef/struct"))
                if pk[0] == "e" and gk[0] == "i":
                    type_cands.append((gname, gf.path + gf.name, gf.type, pf.type, f"{conf:.2f}", f"{hdr}:{gf.line}", "enum-type"))
            # unmatched fields
            for gi, gf in enumerate(gfields):
                if gi not in matched_g and gf.placeholder:
                    plan.append((gname, gf.path + gf.name, "", "", gf.type, "0.00", "unmatched-gc", f"{hdr}:{gf.line}", "", pname))
            matched_p = {pj for _, pj in matches}
            for pj, pf in enumerate(pfields):
                if pj not in matched_p:
                    plan.append((gname, "", pf.name, pf.type, "", "0.00", "unmatched-ps2", f"{hdr}:{gs.line}", f"ps2off={pf.off:#x}", pf.path.rstrip(":") or pname))

    BUILD.mkdir(exist_ok=True)
    if args.struct:
        names = [n for n in gc_structs if n == args.struct or n.lower() == args.struct.lower()]
        if not names:
            # maybe a PS2 name
            for g, p, how in pairs:
                if args.struct in p.split("+"):
                    names.append(g)
        if not names:
            print(f"no GC struct {args.struct}; unmatched? {args.struct in un_gc}")
            return
        for nm in names:
            if nm not in alignments:
                print(f"{nm}: no PS2 counterpart")
                continue
            for gs, ps, gfields, pfields, matches, confs, how, G, P, moved in alignments[nm]:
                print(f"== {gs.kind} {gs.name} ({os.path.relpath(gs.file, ROOT)}:{gs.line}, {len(gfields)} fields)  <->  PS2 {ps.kind} {ps.name} (size {ps.size:#x} , {len(pfields)} fields)  [{how}]")
                mi = {gi: pj for gi, pj in matches}
                mp = {pj: gi for gi, pj in matches}
                gi = pj = 0
                rows = []
                # walk both sequences in order, emitting matched pairs and gaps
                order = []
                i = j = 0
                emitted_p = {b for _, b in moved}
                for (a, b) in matches:
                    while i < a:
                        order.append((i, None, ""))
                        i += 1
                    if (a, b) in moved:
                        order.append((a, b, ""))
                        emitted_p.add(b)
                        i = a + 1
                        continue
                    while j < b:
                        if j not in emitted_p:
                            order.append((None, j, ""))
                            emitted_p.add(j)
                        j += 1
                    order.append((a, b, ""))
                    emitted_p.add(b)
                    i = a + 1
                    j = b + 1
                while i < len(gfields):
                    order.append((i, None, ""))
                    i += 1
                while j < len(pfields):
                    if j not in emitted_p:
                        order.append((None, j, ""))
                    j += 1
                for a, b, note in order:
                    left = fmt_field(gfields[a]) if a is not None else ""
                    right = fmt_field(pfields[b]) if b is not None else ""
                    if a is not None and b is not None:
                        conf, flags = confs[(a, b)]
                        tag = f"{conf:.2f} {','.join(flags + ([note] if note else []))}"
                        arrow = "->" if gfields[a].name != pfields[b].name else "=="
                    else:
                        tag = ""
                        arrow = "  "
                    print(f"  {left:<52} {arrow} {right:<48} {tag}")
                print()
        return

    if args.params:
        report_params(gc_structs)
        return

    # write plan
    with open(BUILD / "ps2_rename_plan.tsv", "w") as fh:
        fh.write("struct\tgc_field\tps2_field\tps2_type\tgc_type\tconfidence\tkind\tlocation\tflags\tps2_struct\n")
        for row in plan:
            fh.write("\t".join(row) + "\n")
    with open(BUILD / "ps2_type_candidates.tsv", "w") as fh:
        fh.write("struct\tgc_field\tgc_type\tps2_type\tconfidence\tlocation\tkind\n")
        seen = set()
        for row in type_cands:
            if row in seen:
                continue
            seen.add(row)
            fh.write("\t".join(row) + "\n")
    with open(BUILD / "ps2_unmatched.txt", "w") as fh:
        fh.write(f"# GC structs with no PS2 counterpart ({len(un_gc)})\n")
        for g in sorted(un_gc):
            locs = ", ".join(f"{os.path.relpath(s.file, ROOT)}:{s.line}" for s in gc_structs[g][:3])
            nfields = sum(len(s.fields) for s in gc_structs[g])
            fh.write(f"{g}\t{nfields}\t{locs}\n")
        fh.write(f"\n# PS2 structs with no GC counterpart ({len(un_ps2)})\n")
        for p in sorted(un_ps2):
            s = ps2_structs[p]
            fh.write(f"{p}\tsize={s.size:#x}\tfields={len(s.fields)}\t{s.file}:{s.line}\n" if s.size is not None else f"{p}\tfields={len(s.fields)}\n")
        fh.write("\n# struct pairs\n")
        for g, p, how in pairs:
            fh.write(f"{g}\t{p}\t{how}\n")
    enum_candidates(ps2_enums, ps2_structs, plan, gc_structs, tc)

    if args.summary or True:
        ph_total = sum(v[0] for v in per_header.values())
        hi = sum(1 for r in plan if r[6] == "placeholder" and float(r[5]) >= 0.8)
        mid = sum(1 for r in plan if r[6] == "placeholder" and 0.6 <= float(r[5]) < 0.8)
        lo = sum(1 for r in plan if r[6] == "placeholder" and float(r[5]) < 0.6)
        named_hi = sum(1 for r in plan if r[6] == "named" and float(r[5]) >= 0.8)
        named_sim = sum(1 for r in plan if r[6] == "named~")
        print(f"PS2: {len(ps2_structs)} structs, {len(ps2_enums)} enums, {len(ps2_typedefs)} typedefs")
        print(f"GC:  {len(gc_structs)} struct names ({sum(len(v) for v in gc_structs.values())} definitions), {len(gc_enums)} enums, {len(gc_typedefs)} typedefs")
        print(f"pairs: {len(pairs)}  (by name {sum(1 for p in pairs if p[2].startswith('name'))}, alias {sum(1 for p in pairs if p[2]=='alias')}, content {sum(1 for p in pairs if p[2].startswith('content'))})")
        print(f"unmatched GC structs: {len(un_gc)}   unmatched PS2 structs: {len(un_ps2)}")
        print(f"placeholder fields in paired structs: {ph_total}; proposals high(>=0.8) {hi}, mid {mid}, low {lo}")
        print(f"renames of already-named fields: high {named_hi}; vendor spelling of near-equal names: {named_sim}")
        print(f"type-name candidates: {len(type_cands)}")
        print()
        print(f"{'header':<40} {'placeholders':>12} {'high':>6} {'named':>6}")
        for hdr, (ph, hi_, nm) in sorted(per_header.items(), key=lambda kv: -kv[1][0]):
            if ph or hi_ or nm:
                print(f"{hdr:<40} {ph:>12} {hi_:>6} {nm:>6}")
        if args.summary:
            print("\nunmatched GC structs (with placeholder fields):")
            for g in sorted(un_gc):
                phs = [f for s in gc_structs[g] for f in flatten(s) if f.placeholder and not f.name.startswith("pad")]
                if phs:
                    print(f"  {g:<28} {len(phs):>4} placeholders  {os.path.relpath(gc_structs[g][0].file, ROOT)}:{gc_structs[g][0].line}")


# ------------------------------------------------------------------ enum candidates


def enum_candidates(ps2_enums, ps2_structs, plan, gc_structs, tc):
    """PS2 enums used as field types of paired structs: our sources' constants assigned/compared
    on the GC field -> candidates for a later enum pass (not applied)."""
    enum_fields = []  # (ps2 enum, ps2 struct, ps2 field)
    for s in ps2_structs.values():
        for f in s.fields:
            base = tc.resolve(f.type, "ps2")[0]
            if base in ps2_enums:
                enum_fields.append((base, s.name, f.name))
    by_ps2 = {(r[9], r[2]): r for r in plan if r[2]}
    src_files = [p for p in (ROOT / "src").rglob("*.cpp")]
    src_text = {}
    for p in src_files:
        src_text[p] = p.read_text(errors="replace")
    rows = []
    for ename, sname, fname in enum_fields:
        row = by_ps2.get((sname, fname))
        if not row:
            continue
        gfield = row[1].split(".")[-1]
        e = ps2_enums[ename]
        values = {v for _, v in e.members}
        pat = re.compile(r"(?:->|\.)" + re.escape(gfield) + r"\s*(?:==|!=|=|<|>|<=|>=)\s*(0x[0-9A-Fa-f]+|\d+)\b")
        hits = defaultdict(int)
        for p, txt in src_text.items():
            for m in pat.finditer(txt):
                v = int(m.group(1), 0)
                if v in values:
                    hits[v] += 1
        if hits:
            names = {v: n for n, v in e.members}
            rows.append((ename, sname, fname, row[0], gfield, ";".join(f"{names[v]}={v}x{c}" for v, c in sorted(hits.items()))))
    # magic constants in functions whose PS2 signature has an enum parameter
    func_enum = defaultdict(set)
    if PS2_FUNCS.exists():
        for line in PS2_FUNCS.read_text(errors="replace").split("\n"):
            m = re.match(r"^/\* [0-9a-f]{8} [0-9a-f]{8} \*/ \S.*?\b([\w:~]+)\((.*)\)\s*\{?\}?$", line)
            if not m:
                continue
            fn = m.group(1).split("::")[-1]
            for prm in m.group(2).split(","):
                prm = re.sub(r"/\*.*?\*/", "", prm).strip()
                d = parse_declarator(prm) if prm else None
                if d and d[0] in ps2_enums:
                    func_enum[fn].add(d[0])
    for fn, enames in sorted(func_enum.items()):
        pat = re.compile(r"\b" + re.escape(fn) + r"\s*\(([^;]*?)\)")
        for ename in enames:
            e = ps2_enums[ename]
            values = {v for _, v in e.members}
            names = {v: n for n, v in e.members}
            hits = defaultdict(int)
            for p, txt in src_text.items():
                for m in pat.finditer(txt):
                    for lit in re.findall(r"(?<![\w.])(0x[0-9A-Fa-f]+|\d+)(?![\w.])", m.group(1)):
                        v = int(lit, 0)
                        if v in values and v != 0:
                            hits[v] += 1
            if hits:
                rows.append((ename, "call:" + fn, "", "", "", ";".join(f"{names[v]}={v}x{c}" for v, c in sorted(hits.items()))))
    with open(BUILD / "ps2_enum_candidates.tsv", "w") as fh:
        fh.write("ps2_enum\tps2_struct_or_call\tps2_field\tgc_struct\tgc_field\tmatched_values\n")
        for r in rows:
            fh.write("\t".join(r) + "\n")


# ------------------------------------------------------------------ parameter names

PARAM_PLACEHOLDER = re.compile(r"^(param_?\d+|arg\d*|[a-e]|p\d|a\d|v\d|x\d|n\d|unused\d*)$")


def parse_ps2_functions():
    funcs = defaultdict(list)  # qualified name -> [param names list]
    for line in PS2_FUNCS.read_text(errors="replace").split("\n"):
        m = re.match(r"^/\* [0-9a-f]{8} [0-9a-f]{8} \*/ (.*?)\b([\w:~]+)\((.*)\)\s*\{?\}?$", line)
        if not m:
            continue
        qn = m.group(2)
        params = []
        for prm in m.group(3).split(","):
            prm = re.sub(r"/\*.*?\*/", "", prm).strip()
            if not prm or prm == "void":
                continue
            d = parse_declarator(prm)
            params.append((d[0] if d else prm, d[1] if d else prm))
        if params and params[0][1] == "this":
            params = params[1:]
        funcs[qn].append(params)
    return funcs


def param_kind(t):
    """coarse kind of a parameter type for the GC/PS2 signature check"""
    t = re.sub(r"\b(const|struct|class|unsigned|signed)\b", "", t).strip()
    if "*" in t or "&" in t or t.lower() in ("mtx", "mtxptr", "vecptr", "fnptr"):
        return "p"
    low = t.lower()
    if low in FLOAT_TYPES:
        return "f"
    if low in INT_TYPES:
        return "i"
    return "S:" + low


def strip_strings(code):
    """blank out string/char literals so identifier renames never touch them"""
    out = []
    i = 0
    while i < len(code):
        c = code[i]
        if c in "\"'":
            j = i + 1
            while j < len(code) and code[j] != c:
                if code[j] == "\\":
                    j += 1
                j += 1
            out.append(c + " " * (j - i - 1) + c)
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def apply_params(rows, files_filter=None):
    """Rename placeholder parameters (definition + body, and the prototypes) per the param plan.
    rows: (location, name, gparams, pparams, renames[(old,new)]) restricted to compatible kinds."""
    by_file = defaultdict(list)
    for r in rows:
        f, ln = r[0].rsplit(":", 1)
        if files_filter and f not in files_filter:
            continue
        by_file[f].append((int(ln), r))
    applied = []
    skipped = []
    protos = defaultdict(list)  # function short name -> [(file, line)]
    for p in sorted((ROOT / "include").rglob("*.h")) + sorted((ROOT / "src").rglob("*.h")):
        for k, l in enumerate(p.read_text(errors="replace").split("\n")):
            m = re.match(r"^\s*(?:static\s+|inline\s+|virtual\s+|extern\s+)*[A-Za-z_][\w:<>]*(?:\s*[\*&]+)?\s+[\*&]*([\w:~]+)\s*\(([^;{)]*)\)\s*(?:const)?\s*(?:=\s*0)?\s*;", l)
            if m:
                protos[m.group(1).split("::")[-1]].append((p, k))
    for f, items in by_file.items():
        p = ROOT / f
        text = p.read_text()
        lines = text.split("\n")
        # names a macro of this file refers to cannot be renamed (the body reaches them by name)
        macro_names = set()
        in_macro = False
        for l in lines:
            if re.match(r"^\s*#\s*define\b", l):
                in_macro = True
            if in_macro:
                macro_names |= set(re.findall(r"[A-Za-z_]\w*", split_comment(l)[0]))
                if not l.rstrip().endswith("\\"):
                    in_macro = False
        for ln, r in sorted(items, reverse=True):
            loc, name, gparams, pparams, renames = r
            renames = [(o, n) for o, n in renames if o not in macro_names]
            if not renames:
                skipped.append((loc, name, "", "", "parameter names appear in this file's macros"))
                continue
            li = ln - 1
            # signature may span lines up to ')' ; find the '{' or ';'
            k = li
            sig = lines[k]
            while ")" not in sig and k + 1 < len(lines):
                k += 1
                sig += "\n" + lines[k]
            body_start = None
            j = k
            probe = "\n".join(lines[li: k + 1])
            if "{" in probe.split(")")[-1]:
                body_start = (k, lines[k].index("{"))
            else:
                jj = k + 1
                while jj < len(lines) and jj < k + 4:
                    if lines[jj].strip().startswith("{"):
                        body_start = (jj, lines[jj].index("{"))
                        break
                    if lines[jj].strip().endswith(";"):
                        break
                    jj += 1
            end_li = None
            if body_start:
                end_li, _ = scan_balanced(lines, body_start[0], body_start[1])
                if end_li >= len(lines):
                    skipped.append((loc, name, "", "", "unbalanced braces after the signature"))
                    continue
            span = range(li, (end_li if end_li is not None else k) + 1)
            body_txt = "\n".join(lines[x] for x in span)
            body_code = strip_strings(strip_block_comments(body_txt))
            ok = True
            for old, new in renames:
                if re.search(r"\b" + re.escape(new) + r"\b", body_code):
                    skipped.append((loc, name, old, new, "new name already used in the function"))
                    ok = False
            if not ok:
                continue
            for old, new in renames:
                pat = re.compile(r"(?<![\w.>])" + re.escape(old) + r"\b(?!\s*::)")
                for x in span:
                    code, com = split_comment(lines[x])
                    masked = strip_strings(code)
                    # rename only at positions that are not inside literals
                    pieces = []
                    last = 0
                    for m in pat.finditer(masked):
                        pieces.append(code[last: m.start()])
                        pieces.append(new)
                        last = m.end()
                    pieces.append(code[last:])
                    lines[x] = "".join(pieces) + ("//" + com if com else "")
            applied.append((loc, name, renames))
            # prototypes elsewhere with the same parameter count and placeholder names
            for pf, pk in protos.get(name.split("::")[-1], []):
                if pf == p and pk == li:
                    continue
                same_file = pf.resolve() == p.resolve()
                plines = lines if same_file else pf.read_text().split("\n")
                pl = plines[pk]
                m = re.search(r"\(([^)]*)\)", pl)
                if not m:
                    continue
                params = [x.strip() for x in m.group(1).split(",") if x.strip()]
                if len(params) != len(gparams):
                    continue
                new_params = []
                changed = False
                for prm, (gt, gn) in zip(params, gparams):
                    d = parse_declarator(re.sub(r"=.*$", "", prm).strip())
                    if d and d[1] == gn and gn in dict(renames):
                        new_params.append(re.sub(r"\b" + re.escape(gn) + r"\b(?!.*\b" + re.escape(gn) + r"\b)", dict(renames)[gn], prm))
                        changed = True
                    else:
                        new_params.append(prm)
                if changed:
                    plines[pk] = pl[: m.start(1)] + ", ".join(new_params) + pl[m.end(1):]
                    if not same_file:
                        pf.write_text("\n".join(plines))
                    applied.append((f"{os.path.relpath(pf, ROOT)}:{pk + 1}", name, [("proto",)] + renames))
        p.write_text("\n".join(lines))
    return applied, skipped


def report_params(gc_structs):
    funcs = parse_ps2_functions()
    short = defaultdict(list)
    for qn, lst in funcs.items():
        short[qn.split("::")[-1]].append((qn, lst))
    # definitions / declarations only: a return type before the name and a typed parameter list
    sig = re.compile(r"^(?:static\s+|inline\s+|virtual\s+|extern\s+)*[A-Za-z_][\w:<>]*(?:\s*[\*&]+)?\s+[\*&]*([\w:~]+)\s*\(([^;{)]*)\)\s*(?:const)?\s*(?:\{|;|:|$)", re.M)
    ptype = re.compile(r"^(?:const\s+)?(?:(?:struct|class|unsigned|signed)\s+)?[A-Za-z_]\w*(?:\s*(?:\*+|&))?(?:\s*const)?$")
    files = sorted((ROOT / "src").rglob("*.cpp")) + sorted((ROOT / "include").rglob("*.h"))
    out = []
    for p in files:
        if "dolphin" in p.parts:
            continue
        txt = p.read_text(errors="replace")
        for m in sig.finditer(txt):
            name = m.group(1)
            params_txt = m.group(2).strip()
            if not params_txt or name in ("if", "while", "for", "switch", "return", "sizeof", "else"):
                continue
            if re.match(r"^\s*(return|else|case|goto|delete|new)\b", txt[m.start():]):
                continue
            gparams = []
            ok = True
            for prm in params_txt.split(","):
                prm = prm.strip()
                if prm in ("void", "...", ""):
                    continue
                prm = re.sub(r"=.*$", "", prm).strip()
                d = parse_declarator(prm)
                if not d or not ptype.match(d[0]):
                    ok = False
                    break
                gparams.append((d[0], d[1]))
            if not ok or not gparams:
                continue
            if not any(PARAM_PLACEHOLDER.match(n) for _, n in gparams):
                continue
            key = name.split("::")[-1]
            cands = funcs.get(name) if "::" in name else None
            if not cands:
                lst = short.get(key, [])
                if "::" in name:
                    cls = name.split("::")[0]
                    lst = [x for x in lst if x[0].startswith(cls + "::")]
                elif len(lst) > 1:
                    lst = [x for x in lst if "::" not in x[0]]
                cands = [pp for _, ll in lst for pp in ll]
            if not cands:
                continue
            same = [c for c in cands if len(c) == len(gparams)]
            if len({tuple(n for _, n in c) for c in same}) != 1:
                continue
            pnames = [n for _, n in same[0]]
            line = txt.count("\n", 0, m.start()) + 1
            # the signatures must agree in kind (pointer / int / float) parameter by parameter
            compatible = True
            for (gt, g), (pt, pn) in zip(gparams, same[0]):
                gk, pk = param_kind(gt), param_kind(pt)
                if gk != pk and not (gk == "i" and pk.startswith("S:")) and not (gk == "p" and pk == "i" and "*" not in gt and gt.lower() in ("mtx",)):
                    compatible = False
            renames = [(g, pn) for (gt, g), pn in zip(gparams, pnames) if PARAM_PLACEHOLDER.match(g) and g != pn and re.match(r"^[A-Za-z_]\w*$", pn) and pn not in ("this",)]
            # a PS2 name that is another GC parameter's name would collide
            gnames = {g for _, g in gparams}
            renames = [(g, pn) for g, pn in renames if pn not in gnames]
            if renames and compatible:
                out.append((f"{os.path.relpath(p, ROOT)}:{line}", name, gparams, same[0], renames))
            elif renames:
                out.append((f"{os.path.relpath(p, ROOT)}:{line}", name, gparams, same[0], []))
    with open(BUILD / "ps2_param_plan.tsv", "w") as fh:
        fh.write("location\tfunction\tgc_params\tps2_params\trenames\n")
        for loc, name, gparams, pparams, renames in out:
            fh.write("\t".join([loc, name, ", ".join(f"{t} {n}" for t, n in gparams), ", ".join(f"{t} {n}" for t, n in pparams),
                                " ".join(f"{a}->{b}" for a, b in renames) or "(signature kinds differ: skipped)"]) + "\n")
    print(f"{len(out)} functions with placeholder parameter names and a PS2 signature -> build/ps2_param_plan.tsv")
    return [r for r in out if r[4]]


# ------------------------------------------------------------------ apply (Task B helper)


def apply_plan(path, min_conf, kinds, only=None, skip=None):
    """Rename the declaration lines of `path` per build/ps2_rename_plan.tsv. Returns the list of
    (struct, old, new) applied; prints skipped rows with the reason. Use sites are left to the
    compiler (`--fix-errors`)."""
    rel = os.path.relpath(Path(path).resolve(), ROOT)
    rows = []
    with open(BUILD / "ps2_rename_plan.tsv") as fh:
        next(fh)
        for line in fh:
            r = line.rstrip("\n").split("\t")
            loc = r[7]
            if not loc.startswith(rel + ":"):
                continue
            rows.append(r)
    lines = Path(path).read_text().split("\n")
    # names already declared per struct (collision check): every field and method of that struct
    struct_names = defaultdict(set)
    gs, ge, gt = {}, {}, {}
    parse_gc_file(Path(path), gs, ge, gt)
    for nm, defs in gs.items():
        for d in defs:
            struct_names[nm] |= {f.name for f in flatten(d)} | set(d.methods)
    for r in rows:
        struct_names[r[0]].add(r[1].split(".")[-1])
    taken = defaultdict(set)
    applied = []
    skipped = []
    for r in rows:
        struct, gfield, pfield, ptype, gtype, conf, kind, loc, flags, pstruct = r
        old = gfield.split(".")[-1]
        if kind not in kinds or float(conf) < min_conf or not pfield:
            continue
        if only and (struct, old) not in only:
            continue
        if skip and (struct, old) in skip:
            skipped.append((struct, old, pfield, "skipped by hand"))
            continue
        if pfield in struct_names[struct] or pfield in taken[struct]:
            skipped.append((struct, old, pfield, "name already used in the struct"))
            continue
        if pfield in ("pad", "padding", "dummy") or re.match(r"^(pad|padding|dummy|Dummy)\d*$", pfield):
            skipped.append((struct, old, pfield, "vendor padding name"))
            continue
        ln = int(loc.split(":")[1]) - 1
        code, com = split_comment(lines[ln])
        new_code, n = re.subn(r"\b" + re.escape(old) + r"\b", pfield, code)
        if n != 1:
            skipped.append((struct, old, pfield, f"declaration not found once on line {ln + 1} ({n})"))
            continue
        # keep the alignment of the trailing comment where possible
        lines[ln] = new_code + ("//" + com if com else "")
        taken[struct].add(pfield)
        struct_names[struct].discard(old)  # the old name is free again (chained renames)
        applied.append((struct, old, pfield, ptype, conf, ln + 1))
    Path(path).write_text("\n".join(lines))
    return applied, skipped


ERR_MEMBER = re.compile(r"^(\S+?):(\d+): `(?:class|struct|union) [\w:]*?(\w+)' has no member named `(\w+)'")
ERR_UNDECL = re.compile(r"^(\S+?):(\d+): `(\w+)' undeclared")
ERR_CALL = re.compile(r"^(\S+?):(\d+): no matching function for call to `(\w+)::(\w+) \(")
ERR_CTX = re.compile(r"^(\S+?): In (?:method|function|member function) `.*?\b(\w+)::(?:operator\s*[^\s(]+|[~\w]+)\s*\(")



def subn_code(pattern, repl, code, count=0):
    """re.subn restricted to the parts of `code` outside string / char literals"""
    parts = re.split(r'("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')', code)
    total = 0
    for i in range(0, len(parts), 2):
        if count and total >= count:
            break
        parts[i], n = re.subn(pattern, repl, parts[i], count=(count - total) if count else 0)
        total += n
    return "".join(parts), total


def fix_errors(errors_text, renames, bare=True):
    """Rename use sites at the exact file:line the compiler reported. `renames` maps
    (struct, old) -> new. Errors are `class X' has no member named `old' (struct known) or
    `old' undeclared inside a method (struct from the preceding In method `X::f(...)' line).
    Returns (fixed, unresolved); ambiguous names are reported, never guessed."""
    fixed = []
    unresolved = []
    by_file = defaultdict(dict)
    unit_of = {}  # reported path -> unit dir (from the FAILED line), for #line disambiguation
    ctx_struct = None
    unit = None
    for line in errors_text.split("\n"):
        m = re.match(r"^FAILED: .*build/G4BE08/(src/\S+)\.o", line)
        if m:
            unit = m.group(1)
            continue
        m = ERR_CTX.match(line)
        if m:
            ctx_struct = m.group(2)
            continue
        m = ERR_MEMBER.match(line)
        if m:
            by_file[m.group(1)][(int(m.group(2)), m.group(4))] = (m.group(3), "member")
            unit_of.setdefault(m.group(1), set()).add(unit)
            continue
        m = ERR_UNDECL.match(line)
        if m:
            by_file[m.group(1)][(int(m.group(2)), m.group(3))] = (ctx_struct, "undecl")
            unit_of.setdefault(m.group(1), set()).add(unit)
            continue
        m = ERR_CALL.match(line)
        if m:
            by_file[m.group(1)][(int(m.group(2)), m.group(4))] = (m.group(3), "member")
            unit_of.setdefault(m.group(1), set()).add(unit)
    by_old = defaultdict(set)
    for (st, old), new in renames.items():
        by_old[old].add(new)
    # sources compiled under a `#line N "D:/Bio4/Prog/x.cpp"` directive report that path
    line_dirs = {}
    for f in list(by_file):
        if f.startswith("Z:/"):
            by_file[os.path.relpath(f[2:], ROOT)] = by_file.pop(f)
    for f in by_file:
        local = (ROOT / f).exists()
        if local:
            txt = (ROOT / f).read_text(errors="replace")
            if not re.search(r"^\s*#\s*line\b", txt, re.M):
                continue
            files = [f]
        else:
            files = subprocess.run(["rg", "-l", "-F", f'"{f}"', "src"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        if True:
            units = {u for u in unit_of.get(f, set()) if u}
            if units:
                udirs = {os.path.dirname(u) for u in units}
                cand = [x for x in files if x in units or os.path.dirname(x) in udirs]
                if cand:
                    files = cand
            ranges = []  # (src, physical line of the directive, reported number there, physical end)
            for src in files:
                cur = src  # before any directive the compiler reports the physical path
                dirs = [(0, 1, src)]
                src_lines = (ROOT / src).read_text(errors="replace").split("\n")
                macros = dict(re.findall(r'^\s*#\s*define\s+(\w+)\s+"([^"]+)"', "\n".join(src_lines), re.M))
                for k, l in enumerate(src_lines):
                    m = re.match(r'^\s*#\s*line\s+(\d+)(?:\s+("([^"]+)"|(\w+)))?', l)
                    if m:
                        if m.group(3):
                            cur = m.group(3)
                        elif m.group(4) and m.group(4) in macros:
                            cur = macros[m.group(4)]
                        dirs.append((k + 1, int(m.group(1)), cur))
                for i, (P, N, name) in enumerate(dirs):
                    end = dirs[i + 1][0] if i + 1 < len(dirs) else 10 ** 9
                    if name == f:
                        ranges.append((src, P, N, end))
            line_dirs[f] = ranges
    for f, sites in by_file.items():
        if f in line_dirs:
            ranges = line_dirs[f]

            def remap(ln, old, ranges=ranges):
                # directives that renumber backwards make the ranges overlap: keep the candidate
                # physical lines that actually contain the name
                out = []
                for src, P, N, end in ranges:
                    phys = P + 1 + (ln - N)
                    if P < phys < end:
                        out.append((src, phys))
                if len(out) > 1:
                    txts = {}
                    hits = []
                    for src, phys in out:
                        txts.setdefault(src, (ROOT / src).read_text(errors="replace").split("\n"))
                        if phys <= len(txts[src]) and re.search(r"\b" + re.escape(old) + r"\b", txts[src][phys - 1]):
                            hits.append((src, phys))
                    out = hits
                return out
            groups = defaultdict(dict)
            for (ln, old), st in sites.items():
                r = remap(ln, old)
                if len(r) != 1:
                    unresolved.append((f, ln, old, f"#line remap: {len(r)} candidate lines"))
                    continue
                r = r[0]
                groups[r[0]][(r[1], old)] = st
            for src, sites2 in groups.items():
                fx, un = fix_errors_file(src, sites2, renames, by_old, bare)
                fixed += fx
                unresolved += un
            continue
        fx, un = fix_errors_file(f, sites, renames, by_old, bare)
        fixed += fx
        unresolved += un
    return fixed, unresolved


def fix_errors_file(f, sites, renames, by_old, bare=True):
    fixed = []
    unresolved = []
    if True:
        p = ROOT / f if not os.path.isabs(f) else Path(f)
        if not p.exists():
            unresolved.append((f, 0, "?", "file not found"))
            return fixed, unresolved
        lines = p.read_text().split("\n")
        bare_done = set()
        reverted = defaultdict(set)  # line -> char offsets of member accesses reverted this pass

        def order(item):
            (ln, old), (st, kind) = item
            is_revert = renames.get((st, old)) is None and not by_old.get(old) and any(nw == old for nw in renames.values())
            return (ln, 0 if is_revert else 1, old)

        for (ln, old), (st, kind) in sorted(sites.items(), key=order):
            new = renames.get((st, old))
            if new is None:
                cands = by_old.get(old, set())
                if len(cands) == 1:
                    new = next(iter(cands))
                elif not cands:
                    # a NEW name of another struct's rename on a line that also accessed this
                    # struct's same-named old field (`w->x2 = gen->x2`): undo the last occurrence
                    back = [(st2, o) for (st2, o), nw in renames.items() if nw == old]
                    if len({o for _, o in back}) == 1:
                        o = back[0][1]
                        code, com = split_comment(lines[ln - 1])
                        # member error: the fixer renames left to right, so the wrong one is the
                        # first `.new`; undeclared: the last bare use
                        if kind == "member":
                            occ = list(re.finditer(r"(?<=[.>])\s*" + re.escape(old) + r"\b", strip_strings(code)))[:1]
                        else:
                            occ = list(re.finditer(r"(?<![\w.>:])" + re.escape(old) + r"\b", strip_strings(code)))
                        if occ:
                            m0 = occ[-1]
                            code = code[: m0.start()] + o + code[m0.end():]
                            lines[ln - 1] = code + ("//" + com if com else "")
                            reverted[ln].add(m0.start())
                            fixed.append((f, ln, old, o, "revert"))
                            continue
                    unresolved.append((f, ln, old, f"not in the applied renames (struct {st})"))
                    continue
                else:
                    unresolved.append((f, ln, old, f"ambiguous in struct {st}: " + "/".join(sorted(cands))))
                    continue
            code, com = split_comment(lines[ln - 1])
            # one occurrence per pass: another struct's same-named field on the line stays valid
            # and is never reported, so it is never renamed. A member error only ever renames a
            # `.old` / `->old` access; an undeclared error only a bare use (locals and parameters
            # of the same name on the line are left alone)
            if kind == "member":
                # skip the occurrence a revert on this line just restored: it belongs to the other struct
                n = 0
                new_code = code
                for m0 in re.finditer(r"(?:\.|->)\s*(" + re.escape(old) + r")\b", strip_strings(code)):
                    if m0.start(1) in reverted.get(ln, ()):
                        continue
                    new_code = code[: m0.start(1)] + new + code[m0.end(1):]
                    n = 1
                    break
            else:
                new_code, n = subn_code(r"(?<![\w.>:])" + re.escape(old) + r"\b", new, code, count=1)
            if n == 0:
                # the use is inside a macro expanded on this line: rename it in the #define
                # of this file (a macro of a header would have failed in every unit anyway)
                # Only the macros named on the line are patched (transitively: macros they use), and a
                # member error only patches `.old` / `->old` accesses in them.
                nm = 0
                macro_of = {}
                k = 0
                while k < len(lines):
                    mdef = re.match(r"^\s*#\s*define\s+(\w+)", lines[k])
                    if mdef:
                        start = k
                        while k < len(lines) - 1 and lines[k].rstrip().endswith("\\"):
                            k += 1
                        macro_of[mdef.group(1)] = (start, k)
                    k += 1
                wanted = set(re.findall(r"\b([A-Za-z_]\w*)\b", code)) & set(macro_of)
                seen = set()
                while wanted - seen:
                    nmac = next(iter(wanted - seen))
                    seen.add(nmac)
                    a_, b_ = macro_of[nmac]
                    body = "\n".join(lines[a_ : b_ + 1])
                    wanted |= set(re.findall(r"\b([A-Za-z_]\w*)\b", body)) & set(macro_of)
                pat = (r"((?:\.|->)\s*)" + re.escape(old) + r"\b") if kind == "member" else (r"(?<![\w.>:])()" + re.escape(old) + r"\b")
                total = sum(len(re.findall(pat, split_comment(lines[k])[0])) for nmac in seen for k in range(*[x + y for x, y in zip(macro_of[nmac], (0, 1))]))
                if total > 1:
                    # several accesses in the macro body may belong to different structs: by hand
                    unresolved.append((f, ln, old, f"macro body has {total} `{old}' accesses; rename by hand"))
                    continue
                for nmac in seen:
                    a_, b_ = macro_of[nmac]
                    for k in range(a_, b_ + 1):
                        c2, cm2 = split_comment(lines[k])
                        c3, n2 = subn_code(pat, r"\g<1>" + new, c2)
                        if n2:
                            lines[k] = c3 + ("//" + cm2 if cm2 else "")
                            nm += n2
                if nm == 0:
                    unresolved.append((f, ln, old, "use not found on the line"))
                    continue
                fixed.append((f, ln, old, new, f"macro x{nm}"))
                continue
            lines[ln - 1] = new_code + ("//" + com if com else "")
            fixed.append((f, ln, old, new, n))
            # `old' undeclared: a bare use inside a method of the struct. GCC reports one per
            # function, so rename every bare (not member-access) use in the file at once; a bare
            # use can only be that struct's field or another struct's same-named one, which the
            # next compile would report as `has no member named new'
            # The pass is scoped to the enclosing function body (`{` .. `}` at column 0) and skipped
            # when that function declares a local or parameter of the same name.
            if bare and kind == "undecl" and st is not None and re.search(r"(?<![\w.>:])" + re.escape(old) + r"\b", code):
                start = ln - 1
                while start > 0 and not lines[start].startswith("{"):
                    start -= 1
                end = ln - 1
                while end < len(lines) - 1 and not lines[end].startswith("}"):
                    end += 1
                if (start, old) in bare_done:
                    continue
                bare_done.add((start, old))
                decl = re.compile(r"^\s*(?:const\s+|static\s+|struct\s+|class\s+|register\s+|volatile\s+)*[A-Za-z_][\w:<>]*\s*[\*&]*\s+[\*&]*" + re.escape(old) + r"\s*(?:\[[^\]]*\]\s*)*(?:;|:\s*\d+|,|=|\))")
                sig = lines[start - 1] if start > 0 else ""
                decl_new = re.compile(r"^\s*(?:const\s+|static\s+|struct\s+|class\s+|register\s+|volatile\s+)*[A-Za-z_][\w:<>]*\s*[\*&]*\s+[\*&]*" + re.escape(new) + r"\s*(?:\[[^\]]*\]\s*)*(?:;|:\s*\d+|,|=|\))")
                if re.search(r"[(,]\s*(?:const\s+)?[\w:<>]+\s*[\*&]*\s*(" + re.escape(old) + "|" + re.escape(new) + r")\s*(?:\[[^\]]*\])?\s*[,)=]", sig) or any(
                    decl.match(split_comment(l)[0]) or decl_new.match(split_comment(l)[0]) for l in lines[start : end + 1]
                ):
                    fixed.append((f, ln, old, new, "bare skipped: local/parameter of that name in the function"))
                    continue
                nb = 0
                for k in range(start, end + 1):
                    c2, cm2 = split_comment(lines[k])
                    c3, n3 = subn_code(r"(?<![\w.>:])" + re.escape(old) + r"\b", new, c2)
                    if n3:
                        lines[k] = c3 + ("//" + cm2 if cm2 else "")
                        nb += n3
                if nb:
                    fixed.append((f, ln, old, new, f"bare x{nb} in function at line {start}"))
        p.write_text("\n".join(lines))
    return fixed, unresolved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--struct")
    ap.add_argument("--params", action="store_true")
    ap.add_argument("--apply", help="header/source to rename declarations in, per the plan")
    ap.add_argument("--min-conf", type=float, default=0.8)
    ap.add_argument("--kinds", default="placeholder")
    ap.add_argument("--only", help="comma list of struct:field to apply (subset)")
    ap.add_argument("--skip", help="comma list of struct:field to leave alone")
    ap.add_argument("--fix-errors", help="file with compiler errors; use sites are renamed per the mapping file")
    ap.add_argument("--map", help="tsv of applied renames (struct old new) used by --fix-errors")
    ap.add_argument("--apply-params", action="store_true", help="rename placeholder parameters per the param plan")
    ap.add_argument("--files", help="comma list of source files to restrict --apply-params to")
    ap.add_argument("--no-bare", action="store_true", help="--fix-errors: only rename the reported line, never every bare use of the name in the file")
    args = ap.parse_args()
    if args.apply_params:
        rows = report_params(None)
        flt = set(args.files.split(",")) if args.files else None
        applied, skipped = apply_params(rows, flt)
        for a in applied:
            print("applied\t" + "\t".join(str(x) for x in a))
        for s_ in skipped:
            print("skipped\t" + "\t".join(str(x) for x in s_))
        return
    if args.apply:
        only = {tuple(x.split(":")) for x in args.only.split(",")} if args.only else None
        skip = {tuple(x.split(":")) for x in args.skip.split(",")} if args.skip else None
        applied, skipped = apply_plan(args.apply, args.min_conf, set(args.kinds.split(",")), only, skip)
        for a in applied:
            print("applied\t" + "\t".join(str(x) for x in a))
        for s_ in skipped:
            print("skipped\t" + "\t".join(str(x) for x in s_))
        return
    if args.fix_errors:
        renames = {}
        for line in Path(args.map).read_text().split("\n"):
            if not line.strip() or line.startswith("#"):
                continue
            struct, old, new = line.split("\t")[:3]
            renames[(struct, old)] = new
        fixed, unresolved = fix_errors(Path(args.fix_errors).read_text(), renames, not args.no_bare)
        for x in fixed:
            print("fixed\t" + "\t".join(str(v) for v in x))
        for x in unresolved:
            print("unresolved\t" + "\t".join(str(v) for v in x))
        return
    run(args)


if __name__ == "__main__":
    main()
