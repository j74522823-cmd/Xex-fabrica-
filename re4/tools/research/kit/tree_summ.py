#!/usr/bin/env python3
"""summ.py <name> [base]  -> /tmp/treerun/res-<name>.tsv (unit, function, words) of every function
bytecmp reports as differing from the split object; if base given, prints regressions/fixes vs it."""
import re, sys, os, glob
name = sys.argv[1]
base = sys.argv[2] if len(sys.argv) > 2 else None
R = f"/tmp/treerun/run-{name}"
FN = re.compile(r"^\s+0x[0-9a-f]+ (\S+): (\d+) words", re.M)

def load(n):
    out = {}   # unit -> {func: words}  ; unit -> None on error
    for p in glob.glob(f"/tmp/treerun/run-{n}/**/*.txt", recursive=True):
        unit = os.path.relpath(p, f"/tmp/treerun/run-{n}")[:-4]
        t = open(p, errors="replace").read()
        if "VERDICT" not in t:
            out[unit] = None
            continue
        out[unit] = {f: int(w) for f, w in FN.findall(t)}
    return out

cur = load(name)
errs = [u for u, v in cur.items() if v is None]
ndiff = sum(1 for v in cur.values() if v)
nfun = sum(len(v) for v in cur.values() if v)
with open(f"/tmp/treerun/res-{name}.tsv", "w") as f:
    for u in sorted(cur):
        if cur[u]:
            for fn, w in sorted(cur[u].items()):
                f.write(f"{u}\t{fn}\t{w}\n")
print(f"[{name}] units {len(cur)}  errors {len(errs)}  units-with-diffs {ndiff}  differing functions {nfun}")
if errs:
    print("  ERR:", " ".join(sorted(errs)[:20]))
if base:
    b = load(base)
    reg, fix, worse, better = [], [], [], []
    for u in sorted(cur):
        if cur[u] is None or b.get(u) is None:
            continue
        for fn, w in cur[u].items():
            if fn not in b[u]:
                reg.append((u, fn, w))
            elif w > b[u][fn]:
                worse.append((u, fn, b[u][fn], w))
            elif w < b[u][fn]:
                better.append((u, fn, b[u][fn], w))
        for fn, w in b[u].items():
            if fn not in cur[u]:
                fix.append((u, fn, w))
    print(f"  vs {base}: REGRESSIONS {len(reg)} (units {len(set(u for u,_,_ in reg))})  "
          f"FIXES {len(fix)}  worse {len(worse)}  better {len(better)}")
    with open(f"/tmp/treerun/cmp-{name}-vs-{base}.txt", "w") as f:
        for kind, lst in (("REG", reg), ("FIX", fix), ("WORSE", worse), ("BETTER", better)):
            for row in lst:
                f.write(kind + "\t" + "\t".join(map(str, row)) + "\n")
    for kind, lst in (("REG", reg), ("FIX", fix), ("WORSE", worse), ("BETTER", better)):
        for row in lst[:12]:
            print("   ", kind, *row)
        if len(lst) > 12:
            print(f"    ... {len(lst)-12} more {kind}")
