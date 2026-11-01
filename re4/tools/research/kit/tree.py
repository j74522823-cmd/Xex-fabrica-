#!/usr/bin/env python3
"""tree.py <name> [--snap DIR] [--units FILE] [--flags "..."] [--cc NAME]

Whole-tree compiler experiment harness (2026-09-22; see docs/research/compiler.md "Whole-tree
hypothesis runs"). Build a candidate cc1plus/cc1 into /tmp/treerun/cc-<name>/, snapshot the tree
(`git archive HEAD src include | tar -x -C /tmp/treerun/snap`), run `tree.py <name>`; ~13 s for 820 units
on 32 cores. A candidate compiler rule is admissible only at 0 regressions.

Whole-tree run: every prodg (ngccc.py) unit of build.ninja compiled with /tmp/treerun/cc-<name>
from a SNAPSHOT of src/ + include/ (default /tmp/treerun/snap), bytecmp'd against the split
objects (tools/bytecmp.py, like variant.sh --no-diff).  Same logic as tools/research/kit/variant.py
compile_variant + bytecmp, minus the per-unit `ninja -t commands` and with the include/src roots
redirected to the snapshot so concurrent edits in the live tree cannot perturb a run.
Output: /tmp/treerun/run-<name>/<unit>.txt, then summ.py."""
import os, re, shlex, subprocess, sys, shutil
import multiprocessing
ROOT = os.environ.get("RE4_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
name = sys.argv[1]
snap = "/tmp/treerun/snap"
units_file = None
extra_flags = []
ccname = name
a = sys.argv[2:]
while a:
    if a[0] == "--snap": snap = a[1]; a = a[2:]
    elif a[0] == "--units": units_file = a[1]; a = a[2:]
    elif a[0] == "--flags": extra_flags = a[1].split(); a = a[2:]
    elif a[0] == "--cc": ccname = a[1]; a = a[2:]
    else: raise SystemExit("bad arg " + a[0])
CC = f"/tmp/treerun/cc-{ccname}"
R = f"/tmp/treerun/run-{name}"
K = f"/tmp/treerun/kit-{name}"
shutil.rmtree(R, ignore_errors=True); shutil.rmtree(K, ignore_errors=True)
os.makedirs(R)
cmds_txt = f"/tmp/treerun/ninja-commands.txt"
if not os.path.exists(cmds_txt):
    out = subprocess.run(["ninja", "-t", "commands"], cwd=ROOT, capture_output=True, text=True).stdout
    open(cmds_txt, "w").write(out)
cmds = [l for l in open(cmds_txt).read().splitlines() if "ngccc.py" in l]
want = None
if units_file:
    want = set(l.split("\t")[0] for l in open(units_file).read().splitlines() if l.strip())
sys.path.insert(0, ROOT + "/tools")

def split_segments(cmd):
    segs, cur = [], []
    for tok in shlex.split(cmd):
        if tok == "&&": segs.append(cur); cur = []
        elif tok.endswith("&&") and len(tok) > 2: cur.append(tok[:-2]); segs.append(cur); cur = []
        else: cur.append(tok)
    if cur: segs.append(cur)
    return segs

def redirect(tok):
    if tok.startswith(f"{ROOT}/include"): return snap + "/include" + tok[len(ROOT) + 8:]
    if tok.startswith(f"{ROOT}/src"): return snap + "/src" + tok[len(ROOT) + 4:]
    return tok

def one(cmd):
    segs = split_segments(cmd)
    comp = segs[0]
    src = comp[comp.index("-c") + 1]            # src/game/x.cpp
    obj = comp[comp.index("-o") + 1]            # build/G4BE08/src/<unit>.o
    unit = re.sub(r"^build/G4BE08/src/(.*)\.o$", r"\1", obj)
    if want is not None and unit not in want: return
    out = f"{K}/{unit}"; os.makedirs(out, exist_ok=True)
    vsrc = f"{snap}/{src}"
    vobj = f"{out}/{os.path.basename(src).rsplit('.', 1)[0]}.o"
    argv = []
    for t in comp:
        if t == src: t = vsrc
        elif t == obj: t = vobj
        elif t == "build/compilers/ProDG/3.9.3-v1.79": t = CC
        elif t.startswith("--depfile"): pass
        argv.append(redirect(t))
    # drop --depfile X
    if "--depfile" in argv:
        i = argv.index("--depfile"); del argv[i:i + 2]
    argv = [t if t.startswith(("-", "/")) or not os.path.exists(f"{ROOT}/{t}") else f"{ROOT}/{t}" for t in argv]
    # same-dir includes of the original source
    fi = next(i for i, t in enumerate(argv) if t == "-I" or t.startswith("-I"))
    argv[fi:fi] = ["-I", os.path.dirname(vsrc)]
    argv = argv[argv.index("--prodg-dir"):] + extra_flags
    log = []
    import ngccc, io, contextlib
    if not getattr(ngccc, "_patched", False):
        orig_place = ngccc.place_linkonce
        ngccc.place_linkonce = lambda s_, asm: orig_place(s_.replace(snap + "/", ROOT + "/", 1), asm)
        ngccc._patched = True
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            rc = ngccc.main(argv)
        except SystemExit as e:
            rc = e.code
    log.append(buf.getvalue())
    if rc != 0 or not os.path.exists(vobj):
        log.append(f"compile failed rc={rc}")
    else:
        for seg in segs[1:]:
            if any("transform_dep.py" in t for t in seg): continue
            seg = [vobj if t == obj else t for t in seg]
            seg = [t if t.startswith(("-", "/")) or not os.path.exists(f"{ROOT}/{t}") else f"{ROOT}/{t}" for t in seg]
            r = subprocess.run(seg, cwd=ROOT, capture_output=True, text=True)
            log.append(r.stdout + r.stderr)
        r = subprocess.run([sys.executable, f"{ROOT}/tools/bytecmp.py", unit], cwd=ROOT, env=dict(os.environ, OBJ=vobj),
                           capture_output=True, text=True)
        log.append(r.stdout + r.stderr)
    os.makedirs(os.path.dirname(f"{R}/{unit}.txt"), exist_ok=True)
    open(f"{R}/{unit}.txt", "w").write("\n".join(log))

os.chdir(ROOT)
with multiprocessing.get_context("fork").Pool(16) as pool:
    pool.map(one, cmds, chunksize=4)
os.execvp(sys.executable, [sys.executable, "/tmp/treerun/summ.py", name, *sys.argv[2:][:0], *(["base"] if name != "base" else [])])
