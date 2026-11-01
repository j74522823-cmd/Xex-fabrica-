"""Check against the real game running in Dolphin.

capture(): boots the debug disc in headless dolphin-emu-nogui (no window, no audio, one
instance under `timeout`), drives the pad through Dolphin's Pipe input until the player model plays a
motion, then dumps the player's MotionWork and parts from the emulated memory (read through
/proc/<pid>/mem: Dolphin maps MEM1 as a 32 MiB shared mapping; the emulator must be our child
for ptrace access) into a .bin whose layout is DUMP_LAYOUT below.

compare(): loads such a dump, finds the motion it plays (MotionWork::pMot is a pointer into the
player archive at PL_DATA_ADDR, so pMot - PL_DATA_ADDR is the archive body offset of the FCV
entry), evaluates the same motion frame with the helper on the same model and reports the max
abs error of the parts' ang/pos/scale, l_mat and mat.

Addresses (config/G4BE08/symbols.txt, include/model.h, src/game/read.cpp):
  pG  = *0x80314BC8, pG->pPlayer at +0x50 (= PL_DATA_ADDR 0x807EC000), pG->Speed +0x70
  pPL = *0x803159F4  (the player cModel)
  cModel: pParts 0xF4, nParts 0x102, Motion 0x1D8 (MotionWork 0xDC bytes)
  cParts (0x1D8 bytes): mat 0x0C, l_mat 0x3C, pParent 0x6C, world 0x70, pos 0x94, ang 0xA0,
          scale 0xAC, pList 0xF4, motParts 0x174 (flags at +0x4C = 0x1C0)

DUMP_LAYOUT (little-endian file written by the host; the game values are converted from
big-endian): magic b'RE4MOT02', u32 nParts, u32 arcOffset (pMot - PL_DATA_ADDR), f32 motFrame,
f32 seqFrame, u16 motAttr, u16 hokanCnt, u32 blendPtr, u32 pad, f32 modelPos[3], modelAng[3],
modelScale[3], then MotionWork raw 0xDC bytes (big-endian as in memory), then per parts: f32
pos[3], ang[3], scale[3], world[3], l_mat[12], mat[12], u32 flags, u32 parentIndex (0xFFFFFFFF =
the model).
"""
import os
import shutil
import stat
import struct
import subprocess
import sys
import time

from . import archive, fcv, modelbin, evalhost

PG_ADDR = 0x80314BC8
PPL_ADDR = 0x803159F4
PL_DATA_ADDR = 0x807EC000
MEM1_BASE = 0x80000000
MEM1_SIZE = 0x2000000

MAGIC = b'RE4MOT02'
MW_SIZE = 0xDC
PARTS_REC = struct.Struct('<3f3f3f3f12f12fII')
HEADER = struct.Struct('<8sIIffHHII9f')


class DolphinMemory:
    def __init__(self, pid):
        self.pid = pid
        self.base = None
        deadline = time.time() + 120
        while self.base is None and time.time() < deadline:
            for line in open(f'/proc/{pid}/maps'):
                if 'dolphin-emu' in line and 'rw-s 00000000' in line:
                    a, b = (int(x, 16) for x in line.split()[0].split('-'))
                    if b - a == MEM1_SIZE:
                        self.base = a
                        break
            if self.base is None:
                time.sleep(0.5)
        if self.base is None:
            raise RuntimeError('MEM1 mapping not found in the Dolphin process')
        self.mem = open(f'/proc/{pid}/mem', 'rb', 0)

    def read(self, addr, n):
        if not MEM1_BASE <= addr < MEM1_BASE + MEM1_SIZE:
            raise ValueError(f'address {addr:#x} outside MEM1')
        self.mem.seek(self.base + addr - MEM1_BASE)
        return self.mem.read(n)

    def u32(self, addr):
        return struct.unpack('>I', self.read(addr, 4))[0]

    def u16(self, addr):
        return struct.unpack('>H', self.read(addr, 2))[0]

    def f32(self, addr):
        return struct.unpack('>f', self.read(addr, 4))[0]


def dolphin_command():
    if shutil.which('dolphin-emu-nogui'):
        return ['dolphin-emu-nogui']
    raise RuntimeError('no Dolphin: dolphin-emu-nogui not in PATH (pacman -S dolphin-emu)')


PAD_INI = """[GCPad1]
Device = Pipe/0/ctrl0
Buttons/A = `Button A`
Buttons/B = `Button B`
Buttons/X = `Button X`
Buttons/Y = `Button Y`
Buttons/Z = `Button Z`
Buttons/Start = `Button START`
D-Pad/Up = `Button D_UP`
D-Pad/Down = `Button D_DOWN`
D-Pad/Left = `Button D_LEFT`
D-Pad/Right = `Button D_RIGHT`
Main Stick/Up = `Axis MAIN Y +`
Main Stick/Down = `Axis MAIN Y -`
Main Stick/Left = `Axis MAIN X -`
Main Stick/Right = `Axis MAIN X +`
C-Stick/Up = `Axis C Y +`
C-Stick/Down = `Axis C Y -`
C-Stick/Left = `Axis C X -`
C-Stick/Right = `Axis C X +`
Triggers/L = `Button L`
Triggers/R = `Button R`
Triggers/L-Analog = `Axis L +`
Triggers/R-Analog = `Axis R +`
"""

DOLPHIN_INI = """[Core]
GFXBackend = Null
DSPHLE = True
CPUThread = True
EnableCheats = False
SIDevice0 = 6
[DSP]
Backend = No Audio Output
EnableJIT = False
[Input]
BackgroundInput = True
[Analytics]
Enabled = False
PermissionAsked = True
[AutoUpdate]
UpdateTrack =
"""


LOGGER_INI = """[Options]
WriteToFile = True
WriteToConsole = False
WriteToWindow = False
Verbosity = 4
[Logs]
OSREPORT = True
OSREPORT_HLE = True
CI = True
SI = True
"""


class Dolphin:
    """A headless Dolphin child process with a pad pipe and memory access."""

    def __init__(self, iso, user_dir='/tmp/mot/dolphin_user', max_seconds=900):
        # one emulator at a time, never outliving a failed attempt
        kill_all()
        self.user_dir = os.path.abspath(user_dir)
        os.makedirs(os.path.join(self.user_dir, 'Config'), exist_ok=True)
        os.makedirs(os.path.join(self.user_dir, 'Pipes'), exist_ok=True)
        with open(os.path.join(self.user_dir, 'Config', 'GCPadNew.ini'), 'w') as f:
            f.write(PAD_INI)
        with open(os.path.join(self.user_dir, 'Config', 'Dolphin.ini'), 'w') as f:
            f.write(DOLPHIN_INI)
        with open(os.path.join(self.user_dir, 'Config', 'Logger.ini'), 'w') as f:
            f.write(LOGGER_INI)
        self.fifo = os.path.join(self.user_dir, 'Pipes', 'ctrl0')
        if os.path.exists(self.fifo) and not stat.S_ISFIFO(os.stat(self.fifo).st_mode):
            os.remove(self.fifo)
        if not os.path.exists(self.fifo):
            os.mkfifo(self.fifo)
        cmd = ['timeout', '-k', '5', str(max_seconds)] + dolphin_command()
        cmd += ['-u', self.user_dir, '-p', 'headless', '-v', 'Null', '-a', 'HLE', '-e', os.path.abspath(iso)]
        self.log = open('/tmp/mot/dolphin_run.log', 'w')
        self.proc = subprocess.Popen(cmd, stdout=self.log, stderr=subprocess.STDOUT)
        # the pipe reader is opened by Dolphin's input backend; open our end without blocking
        self.pipe = None
        deadline = time.time() + 60
        while self.pipe is None and time.time() < deadline:
            try:
                self.pipe = os.open(self.fifo, os.O_WRONLY | os.O_NONBLOCK)
            except OSError:
                time.sleep(0.5)
        if self.pipe is None:
            raise RuntimeError('Dolphin did not open the pad pipe')
        self.pid = self.emulator_pid()
        self.mem = DolphinMemory(self.pid)

    def emulator_pid(self):
        """The dolphin-emu-nogui process (a child of the timeout wrapper)."""
        deadline = time.time() + 60
        while time.time() < deadline:
            out = subprocess.run(['pgrep', '-f', '^dolphin-emu-nogui'], capture_output=True, text=True).stdout.split()
            for pid in out:
                if descends_from(int(pid), self.proc.pid):
                    return int(pid)
            time.sleep(0.5)
        raise RuntimeError('emulator process not found')

    def send(self, cmd):
        os.write(self.pipe, (cmd + '\n').encode())

    def press(self, button, hold=0.15, wait=0.4):
        self.send(f'PRESS {button}')
        time.sleep(hold)
        self.send(f'RELEASE {button}')
        time.sleep(wait)

    def stick(self, x, y):
        self.send(f'SET MAIN {x} {y}')

    def close(self):
        # the emulator runs under the timeout wrapper: kill it by pid, then the wrapper
        for sig in (15, 9):
            try:
                os.kill(self.pid, sig)
            except OSError:
                pass
            time.sleep(0.5)
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        kill_all()
        self.log.close()


def kill_all():
    """No emulator may survive an attempt (command line anchored at the start, so callers'
    command lines mentioning the name are not matched; the comm name is truncated to 15 chars)."""
    subprocess.run(['pkill', '-f', '^dolphin-emu-nogui( |$)'], capture_output=True)
    time.sleep(0.5)


def descends_from(pid, ancestor):
    while pid > 1:
        if pid == ancestor:
            return True
        try:
            with open(f'/proc/{pid}/stat') as f:
                pid = int(f.read().split(') ')[1].split()[1])
        except OSError:
            return False
    return False


def player_state(mem):
    """(pPL, pMot, frame) of the player, or None while no player model exists."""
    ppl = mem.u32(PPL_ADDR)
    if not MEM1_BASE <= ppl < MEM1_BASE + MEM1_SIZE:
        return None
    mw = ppl + 0x1D8
    pmot = mem.u32(mw)
    if pmot == 0:
        return (ppl, 0, 0.0)
    return (ppl, pmot, mem.f32(mw + 0x24))


def dump_player(mem, out_path):
    """Writes the DUMP_LAYOUT file for the player's current motion state."""
    ppl, pmot, frame = player_state(mem)
    mw = ppl + 0x1D8
    raw = mem.read(mw, MW_SIZE)
    n = mem.read(ppl + 0x102, 1)[0]
    parts = []
    p = mem.u32(ppl + 0xF4)
    addrs = []
    while p and len(addrs) < n:
        addrs.append(p)
        p = mem.u32(p + 0xF4)
    if len(addrs) != n:
        raise RuntimeError(f'parts chain has {len(addrs)} entries, nParts {n}')
    index = {a: i for i, a in enumerate(addrs)}
    for a in addrs:
        blob = mem.read(a, 0x1D8)
        pos = struct.unpack('>3f', blob[0x94:0xA0])
        ang = struct.unpack('>3f', blob[0xA0:0xAC])
        scale = struct.unpack('>3f', blob[0xAC:0xB8])
        world = struct.unpack('>3f', blob[0x70:0x7C])
        l_mat = struct.unpack('>12f', blob[0x3C:0x6C])
        mat = struct.unpack('>12f', blob[0x0C:0x3C])
        flags = struct.unpack('>I', blob[0x1C0:0x1C4])[0]
        parent = struct.unpack('>I', blob[0x6C:0x70])[0]
        parts.append(PARTS_REC.pack(*pos, *ang, *scale, *world, *l_mat, *mat, flags, index.get(parent, 0xFFFFFFFF)))
    mot_attr = struct.unpack('>H', raw[0x40:0x42])[0]
    hokan = raw[0xC5]
    blend = struct.unpack('>I', raw[0xD0:0xD4])[0]
    seq_frame = struct.unpack('>f', raw[0xB8:0xBC])[0]
    model = struct.unpack('>9f', mem.read(ppl + 0x94, 36))   # cModel pos / ang / scale
    hdr = HEADER.pack(MAGIC, n, (pmot - PL_DATA_ADDR) & 0xFFFFFFFF, frame, seq_frame, mot_attr, hokan, blend, 0, *model)
    with open(out_path, 'wb') as f:
        f.write(hdr + raw + b''.join(parts))
    return n, pmot - PL_DATA_ADDR, frame, hokan, blend


def read_dump(path):
    d = open(path, 'rb').read()
    hdr = HEADER.unpack_from(d, 0)
    magic, n, arc_ofs, frame, seq_frame, mot_attr, hokan, blend, _ = hdr[:9]
    model = hdr[9:]
    if magic != MAGIC:
        raise ValueError(f'{path}: not a RE4MOT02 dump')
    o = HEADER.size
    raw = d[o:o + MW_SIZE]
    o += MW_SIZE
    parts = []
    for i in range(n):
        rec = PARTS_REC.unpack_from(d, o)
        o += PARTS_REC.size
        parts.append({'pos': rec[0:3], 'ang': rec[3:6], 'scale': rec[6:9], 'world': rec[9:12],
                      'l_mat': rec[12:24], 'mat': rec[24:36], 'flags': rec[36], 'parent': rec[37]})
    return {'n': n, 'arc_ofs': arc_ofs, 'frame': frame, 'seq_frame': seq_frame, 'mot_attr': mot_attr,
            'hokan': hokan, 'blend': blend, 'work': raw, 'parts': parts,
            'model_pos': model[0:3], 'model_ang': model[3:6], 'model_scale': model[6:9]}


def find_entry(arcs, arc_ofs):
    """The archive entry whose body offset is arc_ofs (PL_ARC_PTR = body + ofs[no])."""
    for arc in arcs:
        off = archive.drs.align(16 + 8 * len(arc.drs.entries))
        for i, (tag, data) in enumerate(arc.drs.entries):
            if off == arc_ofs:
                return arc, arc.entry(i)
            off += len(data)
    return None, None


def title_state(mem):
    """(System_flg, pRK->title_shown) of the running game."""
    pg = mem.u32(PG_ADDR)
    prk = mem.u32(0x80315AD4)
    if not (MEM1_BASE <= pg < MEM1_BASE + MEM1_SIZE and MEM1_BASE <= prk < MEM1_BASE + MEM1_SIZE):
        return (0, 0)
    return (mem.u32(pg + 0x54), mem.read(prk + 0x17, 1)[0])


def capture(source, iso, out_path, timeout=600, count=4):
    """Boots the game to the first player motion and dumps `count` distinct frames of it:
    out_path, then out_path with .1 .2 ... inserted. Title flow of the debug disc: logos (skipped
    with START), the 3-entry menu with the cursor on LOAD GAME (UP moves it to NEW GAME, A), then
    the debug game-start menu (A confirms; B leaves the memory card screen if it opens), then the
    opening event: the player model plays its event motions. Returns the dump paths."""
    dol = Dolphin(iso, max_seconds=timeout + 60)
    print(f'dolphin: pid {dol.pid}, MEM1 at {dol.mem.base:#x}', flush=True)
    paths = []
    try:
        t0 = time.time()
        while title_state(dol.mem)[1] != 1:
            if time.time() - t0 > 120:
                raise RuntimeError('title menu not reached')
            dol.press('START')
        time.sleep(2)
        dol.press('D_UP', wait=0.6)
        dol.press('A', wait=0.6)
        time.sleep(4)
        seen = set()
        while time.time() - t0 < timeout:
            st = player_state(dol.mem)
            if st and st[1]:
                ppl, pmot, frame = st
                hokan = dol.mem.read(ppl + 0x1D8 + 0xC5, 1)[0]
                blend = dol.mem.u32(ppl + 0x1D8 + 0xD0)
                if hokan == 0 and blend == 0 and (pmot, frame) not in seen:
                    seen.add((pmot, frame))
                    path = out_path if not paths else f'{os.path.splitext(out_path)[0]}.{len(paths)}{os.path.splitext(out_path)[1]}'
                    info = dump_player(dol.mem, path)
                    print(f'dolphin: dumped {path}: {info[0]} parts, archive offset {info[1]:#x}, frame {info[2]:g}', flush=True)
                    paths.append(path)
                    if len(paths) >= count:
                        return paths
                time.sleep(0.7)
                continue
            flags = title_state(dol.mem)[0]
            dol.press('B' if flags & 0x1000 else 'A', wait=0.6)
            time.sleep(1.5)
        if not paths:
            raise RuntimeError('no player motion within the timeout')
        return paths
    finally:
        dol.close()


def compare(dump_path, arcs, variant='plain', verbose=True):
    """Helper pose vs the dump at the same frame, model placed where the game had it. Three parts
    classes: driven by motion keys only (`keys`), IK chains and blend-table double joints (`ik/blend`:
    frsqrte-based PSVECNormalize/PSVECMag/SQRTF and the paired-single quaternion code on the
    GameCube vs exact sqrt / the SDK's C code here), and parts no motion joint touches (`other`:
    posed by other game code, e.g. the player's head/eye tracking)."""
    d = read_dump(dump_path)
    arc, entry = find_entry(arcs, d['arc_ofs'])
    if entry is None or entry.tag != 'FCV':
        print(f'dump: archive offset {d["arc_ofs"]:#x} is not a motion entry of the given archives')
        return 1
    model = modelbin.parse(arc.entry(0).data)
    model.check_tree()
    if model.n_parts != d['n']:
        print(f'dump: {d["n"]} parts, model {arc.name}:0 has {model.n_parts}')
        return 1
    motion = fcv.parse(entry.data)
    player = evalhost.Player(model, motion, variant=variant)
    player.place(d['model_pos'], d['model_ang'], d['model_scale'])
    pose = player.frame(d['frame'])
    ik_parts = set()
    keyed = set()
    for j in motion.joints:
        if j.target() is not None:
            keyed.add(j.parts_no)
        if j.kind & 0x30:
            ik_parts.update(range(j.parts_no, j.parts_no + 4))
    for dst, a, c, _ in (model.blend_table or []):
        ik_parts.add(dst)
    classes = {'keys': lambda i: i in keyed and i not in ik_parts,
               'ik/blend': lambda i: i in ik_parts,
               'other': lambda i: i not in keyed and i not in ik_parts}
    fields = ['ang', 'pos', 'scale', 'l_mat', 'mat']
    errs = {c: {f: (0.0, -1) for f in fields} for c in classes}
    for i, gp in enumerate(d['parts']):
        cls = next(c for c, test in classes.items() if test(i))
        for f in fields:
            e = max(abs(x - y) for x, y in zip(getattr(pose, f)[i], gp[f]))
            if e > errs[cls][f][0]:
                errs[cls][f] = (e, i)
    print(f'dump {dump_path}: {arc.name} entry {entry.index} (arc {entry.arc_no:#x}), frame {d["frame"]:g}, '
          f'Mot_attr {d["mot_attr"]:#x}, hokan {d["hokan"]}, blend {d["blend"]:#x}, {d["n"]} parts, '
          f'model at {tuple(round(v, 1) for v in d["model_pos"])}; helper variant {variant}')
    print('  max abs error vs the game (mm / rad), worst parts in brackets:')
    for cls in classes:
        n_cls = sum(1 for i in range(d['n']) if classes[cls](i))
        print(f'    {cls:9} ({n_cls:3} parts): ' + '  '.join(f'{f} {errs[cls][f][0]:.2e} [{errs[cls][f][1]}]' for f in fields))
    return 0


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'capture':
        capture(None, sys.argv[2], sys.argv[3])
    elif cmd == 'compare':
        arcs = archive.open_source(sys.argv[3])
        sys.exit(compare(sys.argv[2], arcs))
