#!/usr/bin/env python3
"""RE4 (GameCube) skeletal motion export: every "FCV" motion the game hands to MotionSetCore - the
character archives (files/em/plNN.drs, emNN.drs, wepNN.drs), the yz2-compressed room archives
(files/St*/rNNN.das) with their nested ETM etc archives, the cutscene data (files/Evd/*.evd), the
sub screen data (files/ss/*/*.dat) and the raw .fcv files, on both discs (tools/motion/archive.py) -
evaluated with the game's own code (tools/motion/host) and written as glTF 2.0 (and BVH)
animations on the model's parts hierarchy, with the character's skinned, textured mesh from the
model .bin / .tpl entries.

usage: motion_export.py list <archive|disc>... [--character leon | --all-sources]
       motion_export.py export <archive|disc>... --motion N|name [--archive plNN.drs|rNNN.das|rNNNsMM.evd] [--character leon | --model <bin|[stem:]index>]
                               [--tpl N] [--body-only] [--mesh [stem:]BIN[:[stem:]TPL] ...] [--no-mesh]
                               -o out.gltf [--bvh out.bvh] [--no-ik] [--no-root] [--fps 30] [--scale 0.001]
                               [--blender-check [render_dir] [--strip]] [--render-nice DIR]
       motion_export.py export <archive> --all -o <dir> [--model ...]
       motion_export.py verify <archive|disc>... [--dump <file.bin> | --dolphin] [--fma]

N is the entry index of the archive (the game's PL_ARC index minus 4); an event bin or a room ETM
file is named ('pl0000_s03_000.fcv', 'pl00017.fcv'). --model defaults to the
character table's body of the motion's archive (its entry 0 for the players), its texture palette
to the entry after it (--tpl). The head, hair, eyes, hands ... of a known character come along by
default: the table in tools/motion/character.py, read off the game's set-up code
(cPlLeon::setModel, cPlAda::setModel, cPlAshley::setModel, em10ModelInit ...). --body-only leaves
them out; --mesh adds an attachment (or replaces the palette of one in the table); an entry of
another archive is written 'stem:N' (the weapon-grip hand of the shotgun module for Leon: --mesh
wep04:6:13). An attachment the disc cannot render (empty entry, texture id beyond the palette) is
reported and skipped. --archive picks the archive of a disc.
The player's melee motions are split over two archives (character.MELEE): the kick on a kneeling
enemy is PL_ARC 0x25 of the player's archive (per player: pl0c's is Ada's back kick); the kick on a
stunned enemy (0x29D: Leon's roundhouse and Ada's whirlwind kick are the same bytes), suplex (0xD6),
knee kick / palm strike (0x2B4) and neck break (0x2B9) are entries of the Ganado's archive that the
em10 routines play on the player (`pl->subArc = em->subArc`). `list --character leon` shows them with every
other motion Leon can play (the player archive, the enemy / vehicle archives, the weapon modules,
the rooms, the ETM ladder files, the events, the sub screen) and the game function that plays each
(tools/motion/refs.py, generated from src/ by gen_refs.py); `list --all-sources` is the inventory
per file and tag; `export --archive em10.drs --motion 665 --character leon` plays one on Leon's body.
The PS2 disc is a source of motions (archive.py: BIO4DAT.AFS, archives named NNNN_name.dat after
their AFS index); its models are not read, so a PS2 motion plays on a GameCube body: `export
disc1.iso ps2.iso --archive 0672_ema0.dat --motion 665 --character ada` (Ada's standing kick there).
`verify` decompresses every .das, checks every container (nested ones included), re-serialises
every motion, sequence table and model and counts byte-identical round-trips, decodes every
texture (re-encoding the lossless formats), then compares the helper's poses with a Dolphin memory
dump when given one (see tools/motion/README.md).
"""
import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from motion import archive, fcv, modelbin, meshbin, gxtex, evalhost, gltf, bvh, character  # noqa: E402


def load_motion(entry):
    if entry.tag != 'FCV':
        sys.exit(f'{entry.name}: tag {entry.tag!r}, not a motion (FCV)')
    return fcv.parse(entry.data, entry.endian)


def motion_on_model(entry, motion, model):
    """The motion as it plays on `model`. A PS2 motion on a GameCube body loses the joints of the
    parts the body does not have (the PS2 Ada skeleton's parts 90-97)."""
    if entry.endian == '>':
        return motion
    keep = [i for i, j in enumerate(motion.joints) if j.parts_no < model.n_parts]
    if len(keep) == len(motion.joints):
        return motion
    print(f'  {entry.name}: PS2 joints of parts {sorted(j.parts_no for j in motion.joints if j.parts_no >= model.n_parts)} '
          f'dropped (the GameCube body has {model.n_parts} parts)')
    new = {old: k for k, old in enumerate(keep)}
    return fcv.Motion(motion.max_frame, [motion.joints[i] for i in keep], [new[i] for i in motion.layout if i in new],
                      fill=motion.fill, frame_flags=motion.frame_flags)


def table_body(stem):
    """(stem, entry) of the character table's body for an archive stem, or (stem, 0)."""
    table = character.attachments(stem)
    body = [a for a in table if a.role == 'body'][0] if table else None
    return (stem, body.bin) if body else (stem, 0)


def load_model(ref, arc, src):
    """(skeleton, name, body entry or None for a .bin file). Default: the character table's body
    entry of the motion's archive (em10: 440), else entry 0; 'stem:N' takes the body from another
    archive of the source (the player's, for a melee motion stored in the Ganado's em10.drs)."""
    if ref is None:
        e = arc.entry(table_body(arc.stem)[1])
        if e.tag != 'BIN':
            sys.exit(f'{arc.name} is not in character.TABLE and its entry 0 is {e.tag!r}, not a model: pass '
                     f'--character NAME or --model [stem:]N (a room archive holds no default body)')
    elif os.path.isfile(ref):
        m = modelbin.parse(open(ref, 'rb').read())
        m.check_tree()
        return m, ref, None
    else:
        try:
            e = src.entry(character.parse_ref(ref, arc.stem))
        except MeshSourceError as ex:
            sys.exit(f'--model {ref}: {ex}')
    if e.endian == '<':
        sys.exit(f'{e.name}: PS2 models are not read; give a GameCube disc for the body (--character NAME)')
    if e.tag != 'BIN':
        sys.exit(f'{e.name}: tag {e.tag!r}, not a model (BIN)')
    m = modelbin.parse(e.data)
    m.check_tree()
    return m, e.name, e


class MeshSourceError(Exception):
    pass


def mesh_source(bin_entry, tpl_entry, role=None):
    if bin_entry.endian == '<' or tpl_entry.endian == '<':
        raise MeshSourceError(f'{bin_entry.name}: PS2 models and textures are not read')
    if bin_entry.tag != 'BIN':
        raise MeshSourceError(f'{bin_entry.name}: tag {bin_entry.tag!r}, not a model (BIN)' + (' (empty entry)' if not bin_entry.data else ''))
    if tpl_entry.tag != 'TPL':
        raise MeshSourceError(f'{tpl_entry.name}: tag {tpl_entry.tag!r}, not a texture palette (TPL); pass the TPL entry explicitly')
    mesh = meshbin.parse(bin_entry.data)
    textures = gxtex.parse_tpl(tpl_entry.data)
    # materialSetup binds part.texId (and alphaTex / bumpTex when the flags say so) from the palette:
    # those must exist; the header's nTex may exceed the palette (pl01:6 says 18, uses texture 13 of 17)
    used = {p.tex_id for p in mesh.parts} | {p.alpha_tex for p in mesh.parts if p.flags & 4} | {p.bump_tex for p in mesh.parts if p.flags & 1}
    if max(used) >= len(textures):
        raise MeshSourceError(f'{bin_entry.name}: model uses texture {max(used)}, {tpl_entry.name} has {len(textures)}')
    bstem = os.path.splitext(bin_entry.archive)[0]
    tstem = os.path.splitext(tpl_entry.archive)[0]
    return gltf.MeshSource(mesh, textures, f'{bstem}_{bin_entry.index:03d}', f'{tstem}_{tpl_entry.index:03d}', role)


def parse_mesh_spec(spec, stem):
    """--mesh '[stem:]BIN[:[stem:]TPL]' -> ((stem, bin), (stem, tpl)); TPL defaults to BIN + 1."""
    toks = spec.split(':')
    refs = []
    while toks:
        if toks[0].isdigit() or toks[0].lower().startswith('0x'):
            refs.append((stem, int(toks.pop(0), 0)))
        elif len(toks) >= 2:
            refs.append((toks[0], int(toks[1], 0)))
            toks = toks[2:]
        else:
            sys.exit(f'--mesh {spec}: expected [stem:]BIN[:[stem:]TPL]')
    if len(refs) == 1:
        refs.append(None)
    if len(refs) != 2:
        sys.exit(f'--mesh {spec}: expected [stem:]BIN[:[stem:]TPL]')
    return refs[0], refs[1]


class Source:
    """The archives the sources offer: every archive of a disc (em/*.drs, the St*/rNNN.das rooms,
    St*/*.dat, etc/*.das, op/*.das, ss/*/*.dat + *.fcv, Evd/*.evd, etc/*/*.eff; both discs when
    both are given, a file present on both counted once), or container files and the sibling files
    of their directories (a cross-archive reference 'wep04:6' or 'em10:665' next to pl00.drs)."""

    def __init__(self, paths):
        if isinstance(paths, str):
            paths = [paths]
        self.arcs = {}
        self.is_disc = all(archive.is_disc(p) for p in paths)
        self.dirs = []
        for p in paths:
            for a in archive.open_source(p):
                if a.name in self.arcs:
                    if os.path.getsize(a.path) != os.path.getsize(self.arcs[a.name].path):
                        sys.exit(f'{a.name}: two different files of that name in the sources ({self.arcs[a.name].path}, {a.path})')
                    continue
                self.arcs[a.name] = a
            if not archive.is_disc(p):
                self.dirs.append(os.path.dirname(os.path.abspath(p)))

    def get(self, stem):
        for ext in archive.EXTS:
            name = stem + ext
            if name in self.arcs:
                return self.arcs[name]
        for d in self.dirs:
            for ext in archive.EXTS:
                p = os.path.join(d, stem + ext)
                if os.path.isfile(p):
                    self.arcs[stem + ext] = archive.Archive(p)
                    return self.arcs[stem + ext]
        return None

    def by_kind(self, kind):
        return [a for a in self.arcs.values() if a.kind == kind]

    def rooms(self):
        return [a for a in self.arcs.values() if a.kind == 'hakase' and a.stem.startswith('r') and a.ext == '.das']

    def events(self):
        return self.by_kind('evd')

    def entry(self, ref):
        stem, idx = ref
        arc = self.get(stem)
        if arc is None:
            raise MeshSourceError(f'{stem}:{idx}: archive {stem}.drs / .das not in the source')
        if idx >= len(arc):
            raise MeshSourceError(f'{stem}:{idx}: the archive has {len(arc)} entries')
        return arc.entry(idx)


def load_meshes(args, src, body):
    """[MeshSource]: the body .bin with its TPL (--tpl, default: the entry after the body), the
    character's attachments from character.TABLE when the body's archive is known (head, hair,
    hands ... as the game's setModel loads them; --body-only leaves them out) and every --mesh
    spec, which adds a model or replaces the palette of a table entry."""
    if args.no_mesh:
        return None
    if body is None:
        sys.exit('--model is a file: pass --no-mesh (no texture palette to go with it)')
    stem = os.path.splitext(body.archive)[0]
    body_ref = (stem, body.index)
    tpl_ref = (stem, args.tpl if args.tpl is not None else body.index + 1)
    wanted = [(body_ref, tpl_ref, 'body', 'the model archive')]
    table = character.attachments(stem)
    if args.body_only:
        pass
    elif table is None:
        print(f'note: {stem} is not in character.TABLE: body only (add attachments with --mesh)')
    elif body_ref != table_body(stem):
        print(f'note: --model {body.index} is not the character table\'s body ({table_body(stem)[1]}): body only')
    else:
        for a in table:
            if a.role == 'body':
                if args.tpl is None:
                    wanted[0] = (body_ref, character.ref(a.tpl, stem), 'body', a.source)
                continue
            wanted.append((character.ref(a.bin, stem), character.ref(a.tpl, stem), a.role, a.source))
    for spec in args.mesh or []:
        b, t = parse_mesh_spec(spec, stem)
        for i, w in enumerate(wanted):
            if w[0] == b:
                wanted[i] = (b, t or w[1], w[2], f'--mesh {spec}')
                break
        else:
            wanted.append((b, t or (b[0], b[1] + 1), 'mesh', f'--mesh {spec}'))
    srcs = []
    for b, t, role, source in wanted:
        try:
            srcs.append(mesh_source(src.entry(b), src.entry(t), role))
        except MeshSourceError as e:
            if role == 'body':
                sys.exit(str(e))
            # the disc cannot draw it either (pl02: empty hand entry, hand texture beyond the palette)
            print(f'note: {role} skipped: {e}')
    print('  models: ' + ', '.join(f'{s.role} {s.label} (tpl {s.tex_prefix})' for s in srcs))
    return srcs


def pick_archive(args, src):
    arcs = list(src.arcs.values())
    if len(arcs) == 1:
        return arcs[0]
    if not args.archive:
        sys.exit('a disc holds many archives: pass --archive plNN.drs (or rNNN.das, rNNNsMM.evd)')
    if args.archive not in src.arcs:
        sys.exit(f'{args.archive}: not on the disc')
    return src.arcs[args.archive]


def find_entry(arc, ref):
    """--motion N (entry index) or a name: an event bin / raw file name ('em1000_s00_000.fcv'), or a
    nested ETM file ('ETM/pl00017.fcv' or 'pl00017.fcv') of a room."""
    if ref.isdigit() or ref.lower().startswith('0x'):
        return arc.entry(int(ref, 0))
    e = arc.find(ref)
    if e is None:
        for sub in arc.entries(deep=True):
            if sub.sub and (sub.sub == ref or sub.sub.split('/', 1)[-1] == ref):
                return sub
        sys.exit(f'{arc.name}: no entry named {ref!r}')
    return e


def list_melee(src, stem):
    """The player's melee motions (character.MELEE): the entries the em10 routines play on the
    player, from the player's archive and the Ganado's."""
    rows = character.melee(stem)
    if not rows:
        return
    print(f'melee motions of {stem} (em10/em10.cpp, pl->subArc = em->subArc):')
    for arc_stem, m in rows:
        arc = src.get(arc_stem)
        if arc is None:
            print(f'  {arc_stem}:{m.index}  {m.role}: archive not in the source')
            continue
        e = arc.entry(m.entry)
        desc = describe_entry(e)
        print(f'  {arc_stem}:{e.index:<3} arc {e.arc_no:#05x} {m.role:<16} {desc}')
        print(f'      {m.source}')


def describe_entry(e):
    if e.endian == '<' and e.tag in ('BIN', 'TPL'):
        return f'{e.tag}  PS2 format, not read ({len(e.data):#x} bytes)'
    if e.tag == 'FCV':
        try:
            m = fcv.parse(e.data, e.endian)
            kinds = sorted(set(j.target() or ('root_pos' if j.is_root_pos() else 'root_rot') for j in m.joints))
            ik = sum(1 for j in m.joints if j.kind & 0x30)
            notes = ''
            if e.is_camera:
                notes = ' [camera motion]'
            elif e.is_face:
                notes = ' [face shape data]'
            elif len(m.joints) and all(j.target() is None and not j.is_root_pos() and not j.is_root_rot() for j in m.joints):
                notes = ' [no rot/pos/scale joints]'
            return (f'FCV  {m.max_frame + 1:4} frames, {len(m.joints):2} joints ({", ".join(kinds)}), {ik} IK chains, '
                    f'parts <= {max([j.parts_no for j in m.joints], default=-1)}{notes}')
        except Exception as ex:
            return f'FCV  MALFORMED: {ex}'
    if e.tag == 'SEQ':
        try:
            s = fcv.parse_seq(e.data, e.endian)
            return (f'SEQ  {len(s.keys)} keys, flags {s.flags:#x}, frames {s.keys[0].frame_f:g}..{s.keys[-1].frame_f:g}'
                    if s.keys else 'SEQ  empty')
        except Exception as ex:
            return f'SEQ  not a MotionSeqKey table: {ex}'
    if e.tag == 'BIN':
        try:
            m = modelbin.parse(e.data)
            kind = 'skeleton' if all(p.attach == p.no for p in m.parts) else 'attachment model'
            return f'BIN  {kind}, {m.n_parts} parts, version {m.version:#x}; mesh: {meshbin.describe(meshbin.parse(e.data))}'
        except Exception as ex:
            return f'BIN  ({ex})'
    if e.tag == 'TPL':
        try:
            ts = gxtex.parse_tpl(e.data)
            return f'TPL  {len(ts)} textures: ' + ', '.join(
                f'{t.fmt_name} {t.width}x{t.height}' + (f' {t.max_lod + 1} mips' if t.max_lod else '') for t in ts)
        except Exception as ex:
            return f'TPL  ({ex})'
    return f'{e.tag or "----":4} {len(e.data):#x} bytes'


def motion_round_trips(arc, e):
    """parse + serialise gives the entry's bytes back (ValueError when it does not parse). The raw
    ss/<lang>/*.fcv files end at the last key without the padding their size word counts."""
    out = fcv.serialise(fcv.parse(e.data, e.endian), e.endian)
    if out == e.data:
        return True
    return arc.kind == 'fcv' and out.startswith(e.data) and len(out) - len(e.data) < fcv.ALIGN


def entry_line(e):
    """One listing line: '[idx] arc 0xNN TAG ...' or, for a named / nested entry, its name."""
    if e.sub:
        return f'  [{e.index:3}]   {e.sub:<40} {describe_entry(e)}'
    if e.label:
        return f'  [{e.index:3}] {e.label:<44} {describe_entry(e)}'
    return f'  [{e.index:3}] arc {e.arc_no:#05x} {describe_entry(e)}'


def list_archive(arc, deep=True):
    head = f'{arc.name}: {arc.kind}'
    if arc.kind == 'hakase':
        arc.drs
        if arc.das and arc.das.compressed:
            head += f' (yz2 {arc.das.packed:#x} -> {arc.das.unpacked:#x} bytes)'
    print(head)
    for e in arc.entries(deep=deep):
        if e.tag or e.sub:
            print(entry_line(e))


def refs_lines(calls, indent='        '):
    return ''.join(f'\n{indent}<- {c}' for c in sorted(set(calls)))


def list_character(src, stem):
    """Every motion the player can play, per archive, with the game function that plays it."""
    arc = src.get(stem)
    if arc is None:
        sys.exit(f'{stem}: not in the source')
    pl_type, wep_table, module, em_table = character.PLAYER_TYPE[stem]
    print(f'== {arc.name}: the player archive (ReadPlayerData pl_type {pl_type}; PL_ARC_PTR(pG->pPlayer, n), '
          f'pl_mod.h PL_ARC(n), pl->subArc outside a grab)')
    prefs = character.player_archive_refs(stem)
    n_ref = 0
    for e in arc.entries('FCV'):
        calls = prefs.get(e.arc_no, [])
        n_ref += bool(calls)
        print(entry_line(e) + refs_lines(calls))
    print(f'   {sum(1 for _ in arc.entries("FCV"))} motions, {n_ref} referenced by a constant PL_ARC index in src/ '
          f'(the rest are reached through tables: m_MotTbl, the weapon routines\' PL_ARC_PTR(arc, n) with a computed n, ...)')
    list_melee(src, stem)
    print(f'== enemy / vehicle / partner archives whose motions the game plays on the player '
          f'(pl->subArc = em->subArc; PL_ARC_PTR(em->subArc, n) with the player as the model; {em_table})')
    for em_stem, idx in sorted(character.enemy_archive_refs_on_player(stem).items()):
        a = src.get(em_stem)
        print(f'  {em_stem}.drs:' + ('' if a else ' (archive not in the source)'))
        for i, calls in sorted(idx.items()):
            if a and i - archive.ARC_INDEX_BASE < len(a):
                e = a.entry(i - archive.ARC_INDEX_BASE)
                print('  ' + entry_line(e) + refs_lines(calls, '          '))
            else:
                print(f'    arc {i:#05x}' + refs_lines(calls, '          '))
    print(f'== weapon modules (ReadWepData: read.cpp {wep_table} -> em/wepNN.drs at WEP_DATA_ADDR; WEP_ARC_PTR(n))')
    for wep, nos in character.weapon_archives(stem):
        a = src.get(wep)
        wrefs = character.weapon_archive_refs(wep)
        print(f'  {wep}.drs (weapon no {", ".join(f"{n:#x}" for n in nos)}):' + ('' if a else ' archive not in the source'))
        if a is None:
            for i, calls in sorted(wrefs.items()):
                print(f'    arc {i:#05x}' + refs_lines(calls, '          '))
            continue
        for e in a.entries('FCV'):
            print('  ' + entry_line(e) + refs_lines(wrefs.get(e.arc_no, []), '          '))
    print('== room archives: motions the room scripts play on the player (ROOM_ARC_PTR(pG->pRoom, n): '
          'pPL->motionSet, MotionSetCore(pPL, ..), PlRegistMotion -> m_MotTbl2)')
    for room, idx in sorted(character.room_refs_on_player().items()):
        a = src.get(room)
        print(f'  {room}.das:' + ('' if a else ' (archive not in the source)'))
        for i, calls in sorted(idx.items()):
            if a and i - archive.ARC_INDEX_BASE < len(a):
                print('  ' + entry_line(a.entry(i - archive.ARC_INDEX_BASE)) + refs_lines(calls, '          '))
            else:
                print(f'    arc {i:#05x}' + refs_lines(calls, '          '))
    print(f'== room ETM files named {stem}NNN.fcv (EtcModel.cpp GetEtcAddr: the ladder / door objects play them on the player, '
          f'Et06_init -> cObjLadder::setMotion)')
    n = 0
    for room in sorted(src.rooms(), key=lambda a: a.name):
        for e in room.entries('FCV', deep=True):
            if e.sub and e.sub.startswith(f'ETM/{stem}'):
                print(f'  {room.stem}' + entry_line(e))
                n += 1
    print(f'   {n} files' + ('' if src.rooms() else ' (no room archives in the source)'))
    pat = re.compile(rf'/{stem}\w*/')
    print(f'== events (Evd/*.evd bins event/<room>/<cut>/{stem}NN/*.fcv: Event::ExePacket_Mot on the cut\'s model of that name; '
          f'{stem}NN/face/*.fcv are its ShapeData for ExePacket ShapeSet)')
    n = faces = 0
    for ev in sorted(src.events(), key=lambda a: a.name):
        for e in ev.entries('FCV'):
            if pat.search(e.label):
                print(f'  {ev.stem}' + entry_line(e))
                if e.is_face:
                    faces += 1
                else:
                    n += 1
    print(f'   {n} event motions, {faces} face shape tables' + ('' if src.events() else ' (no Evd/*.evd in the source)'))
    print('== sub screen (Sscrn: the player model built from PL_ARC(4) on the codec screen; SS_ARC_PTR(arc, n) indexes the '
          'offset table like PL_ARC: entry n - 4)')
    for pattern, arc_no, why in character.SS_MOTIONS.get(stem, []):
        names = sorted(a.name for a in src.by_kind('body') if re.fullmatch(pattern.replace('.', r'\.').replace('*', '.*'), a.name))
        if not names:
            print(f'  {pattern} arc {arc_no:#05x}: not in the source\n        <- {why}')
        for name in names:
            print('  ' + entry_line(src.arcs[name].entry(arc_no - archive.ARC_INDEX_BASE)).replace('[', f'{name} [', 1) + f'\n        <- {why}')


def list_all_sources(src):
    """The full inventory: per file, per tag, counts (nested ETM / EFF / SMD entries included), then
    totals per directory and per tag."""
    import collections
    totals = collections.Counter()
    per_dir = collections.Counter()
    fcv_ok = fcv_total = 0
    for a in sorted(src.arcs.values(), key=lambda a: (os.path.dirname(a.path), a.name)):
        c = collections.Counter()
        for e in a.entries(deep=True):
            key = (e.tag or '(empty)') + (f' in {e.sub.split("/")[0]}' if e.sub else '')
            c[key] += 1
            totals[key] += 1
            per_dir[(os.path.basename(os.path.dirname(a.path)), key)] += 1
            if e.tag == 'FCV':
                fcv_total += 1
                try:
                    fcv_ok += motion_round_trips(a, e)
                except ValueError:
                    pass
        extra = ''
        if a.kind == 'hakase' and a.das and a.das.compressed:
            extra = f', yz2 {a.das.packed:#x} -> {a.das.unpacked:#x}'
        print(f'{os.path.relpath(a.path, os.path.commonpath([x.path for x in src.arcs.values()]))}: {a.kind}{extra}; '
              + ', '.join(f'{k} {v}' for k, v in sorted(c.items())))
    print('\nper directory:')
    for d in sorted(set(k[0] for k in per_dir)):
        print(f'  {d}: ' + ', '.join(f'{k[1]} {v}' for k, v in sorted(per_dir.items()) if k[0] == d))
    print('\ntotals: ' + ', '.join(f'{k} {v}' for k, v in sorted(totals.items())))
    print(f'  {fcv_total} FCV entries, {fcv_ok} parse and re-serialise byte-identically')


def cmd_list(args):
    src = Source(args.source)
    if args.character:
        list_character(src, character.character_stem(args.character))
    elif args.all_sources:
        list_all_sources(src)
    else:
        for arc in src.arcs.values():
            list_archive(arc)


def play(model, motion, args):
    player = evalhost.Player(model, motion, variant='fma' if args.fma else 'plain', ik=not args.no_ik)
    return [player.frame(f) for f in range(motion.n_frames)]


def entry_file_stem(arc, e):
    """Output name of a motion: plNN_NNN, or the bin / file name of a named / nested entry."""
    if e.sub or e.label:
        base = os.path.splitext(os.path.basename((e.sub or e.label).strip()))[0]
        return f'{arc.stem}_{base}'
    return f'{arc.stem}_{e.index:03d}'


def export_one(arc, entry, model, model_name, meshes, out, args):
    if entry.is_camera:
        sys.exit(f'{entry.name}: a camera motion (CameraControl::MotionSet), not a skeletal one')
    if entry.is_face:
        sys.exit(f'{entry.name}: face shape data (ShapeSet), not a skeletal motion')
    motion = motion_on_model(entry, load_motion(entry), model)
    poses = play(model, motion, args)
    name = entry_file_stem(arc, entry)
    if meshes and meshes[0].label.rsplit('_', 1)[0] != arc.stem:   # a melee motion on another archive's body
        name += '_' + meshes[0].label.rsplit('_', 1)[0]
    extras = {'re4': {'archive': arc.name, 'entry': entry.index, 'arc_index': entry.arc_no, 'name': entry.sub or entry.label, 'model': model_name,
                      'max_frame': motion.max_frame, 'fps': args.fps, 'units': f'mm x {args.scale}',
                      'ik': not args.no_ik,
                      'meshes': [{'label': s.label, 'role': s.role, 'palette': s.tex_prefix, 'shape_keys': s.shape_names()}
                                 for s in meshes] if meshes else [],
                      'joints': [{'kind': j.kind, 'channel': j.channel, 'fcc_type': j.fcc_type, 'parts': j.parts_no}
                                 for j in motion.joints]}}
    _, stats = gltf.export(model, motion, poses, out, name, fps=args.fps, scale=args.scale, root_motion=not args.no_root,
                           extras=extras, meshes=meshes)
    print(f'{entry.name}: {motion.n_frames} frames, {len(motion.joints)} joints -> {out}')
    if meshes:
        print(f'  mesh: {stats["meshes"]} .bin, {stats["vertices"]} vertices, {stats["triangles"]} triangles, {stats["materials"]} materials'
              + (f', {stats["duplicate_faces"]} duplicate face(s) dropped' if stats['duplicate_faces'] else '')
              + ''.join(f'; {k}: shape keys {", ".join(v)}' for k, v in stats['shape_keys'].items()))
    if args.bvh:
        bvh_path = args.bvh if not args.all else os.path.splitext(out)[0] + '.bvh'
        bvh.export(model, poses, bvh_path, fps=args.fps, scale=args.scale, name=name)
        print(f'  BVH -> {bvh_path}')
    if args.blender_check is not None or args.render_nice:
        blender_check(model, motion, poses, out, name, stats if meshes else None, args)


def blender_check(model, motion, poses, out, name, mesh_stats, args):
    """Headless Blender import of `out` (tools/motion/blender_check.py): bone count, frame range,
    bone world positions against the helper's parts world positions (glTF Y-up -> Blender Z-up:
    (x, y, z) -> (x, -z, y)), the mesh's vertex / triangle counts, 4 rendered frames (textured
    when there is a mesh) and, with --strip, every frame at 30 fps as a film strip + mp4."""
    import json
    import subprocess
    n = motion.n_frames
    frames = sorted(set([0, n // 3, (2 * n) // 3, n - 1]))
    samples = {}
    for f in frames:
        pose = poses[f]
        bones = {}
        for i in range(model.n_parts):
            w = pose.world[i]
            if args.no_root:
                x, y, z = w
            else:   # the model node carries the root keys: world = RotMatrix(root_rot) * parts + root_pos
                m = pose.root_mat
                x = m[0] * w[0] + m[1] * w[1] + m[2] * w[2] + pose.root_pos[0]
                y = m[4] * w[0] + m[5] * w[1] + m[6] * w[2] + pose.root_pos[1]
                z = m[8] * w[0] + m[9] * w[1] + m[10] * w[2] + pose.root_pos[2]
            bones[f'parts_{i:03d}'] = [x * args.scale, -z * args.scale, y * args.scale]
        samples[str(f)] = bones
    ref = {'name': name, 'bones': model.n_parts, 'frames': n, 'fps': args.fps, 'units': f'mm x {args.scale}', 'scale': args.scale,
           'tolerance': 2e-4 * args.scale / 0.001, 'samples': samples, 'mesh': mesh_stats, 'strip': bool(args.strip),
           'nice': args.render_nice}
    ref_path = os.path.splitext(out)[0] + '.ref.json'
    with open(ref_path, 'w') as f:
        json.dump(ref, f)
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'motion', 'blender_check.py')
    cmd = ['blender', '-b', '--python', script, '--', out, ref_path]
    if args.blender_check:
        cmd.append(args.blender_check)
    r = subprocess.run(cmd, capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if l.startswith('blender:')]
    print('\n'.join('  ' + l for l in lines))
    if r.returncode or 'blender: OK' not in lines:
        sys.exit(f'blender check failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}')


def cmd_export(args):
    src = Source(args.source)
    arc = pick_archive(args, src)
    if args.character:
        if args.model:
            sys.exit('--character and --model: pass one')
        stem = character.character_stem(args.character)
        args.model = f'{stem}:{table_body(stem)[1]}'
    model, model_name, body = load_model(args.model, arc, src)
    meshes = load_meshes(args, src, body)
    if args.all:
        os.makedirs(args.output, exist_ok=True)
        for e in arc.entries('FCV', deep=True):
            if e.is_camera or e.is_face:
                continue
            try:
                m = fcv.parse(e.data, e.endian)
            except ValueError as ex:
                print(f'{e.name}: skipped, malformed motion ({ex})')
                continue
            if e.endian == '>' and any(j.target() is not None and j.parts_no >= model.n_parts for j in m.joints):
                print(f'{e.name}: skipped, targets parts beyond the model ({model.n_parts})')
                continue
            out = os.path.join(args.output, entry_file_stem(arc, e) + '.gltf')
            export_one(arc, e, model, model_name, meshes, out, args)
        return
    if args.motion is None:
        sys.exit('export: --motion N or --all')
    export_one(arc, find_entry(arc, args.motion), model, model_name, meshes, args.output, args)


def cmd_verify(args):
    import collections
    src = Source(args.source)
    arcs = list(src.arcs.values())
    total = ok = cam_total = face_total = placeholders = 0
    seq_total = seq_ok = 0
    bin_total = bin_ok = shaped = shape_keys = 0
    tpl_total = tex_total = tex_lossless = tex_ok = 0
    das_total = das_yz2 = das_ok = 0
    das_entries = 0
    ps2_models = 0
    kinds = collections.Counter()
    nested = collections.Counter()
    failures = []
    for arc in list(arcs):
        kinds[arc.kind] += 1
        # .das: the yz2 decode + the container parse (drs.Drs asserts the entry table: offsets
        # ascending, 0x20-aligned, within the body; the record table; the sound bank)
        if arc.ext == '.das':
            das_total += 1
            try:
                arc.drs
            except (AssertionError, ValueError, IndexError) as ex:
                failures.append(f'{arc.name}: {type(ex).__name__}: {ex}')
                arcs.remove(arc)
                continue
            das_yz2 += arc.das.compressed
            das_entries += len(arc.drs.entries)
            bad = [f'entry {i} tag {t!r}' for i, (t, _) in enumerate(arc.drs.entries)
                   if t != b'\0\0\0\0' and not (t[3] == 0 and all(48 <= c <= 90 for c in t[:3]))]
            if arc.das.compressed and arc.das.unpacked % 0x20:
                bad.append(f'unpacked size {arc.das.unpacked:#x} not 0x20-aligned')
            if arc.das.compressed and not 0 <= arc.das.used - arc.das.packed <= 4:
                bad.append(f'coder read {arc.das.used:#x} of a {arc.das.packed:#x} packed stream')
            failures += [f'{arc.name}: {b}' for b in bad]
            das_ok += not bad
        else:
            # the other containers: the parse itself checks the table (bins contiguous and inside
            # the block, ETM records aligned and ending at the entry)
            try:
                len(arc)
            except (ValueError, struct.error) as ex:
                failures.append(f'{arc.name}: {type(ex).__name__}: {ex}')
                arcs.remove(arc)
                continue
    for arc in arcs:
        try:
            entries = list(arc.entries(deep=True))
        except (ValueError, struct.error) as ex:
            failures.append(f'{arc.name}: nested container: {type(ex).__name__}: {ex}')
            entries = list(arc.entries())
        for e in entries:
            if e.sub:
                nested[e.sub.split('/')[0]] += 1
            if e.endian == '<' and e.tag in ('BIN', 'TPL'):
                ps2_models += 1
            elif e.tag == 'BIN':
                bin_total += 1
                try:
                    m = meshbin.parse(e.data)
                    if m.shapes:
                        shaped += 1
                        shape_keys += len(m.shapes)
                    if meshbin.serialise(m) == e.data:
                        bin_ok += 1
                    else:
                        failures.append(f'{e.name}: model re-serialisation differs')
                except ValueError as ex:
                    failures.append(f'{e.name}: model {ex}')
            elif e.tag == 'TPL':
                if e.label and e.data == b' ' * len(e.data):
                    placeholders += 1     # an event bin the packer filled with spaces (32 bytes): no palette
                    continue
                tpl_total += 1
                try:
                    ts = gxtex.parse_tpl(e.data)
                    tex_total += len(ts)
                    n, k, f = gxtex.verify(ts)
                    tex_lossless += n
                    tex_ok += k
                    failures += [f'{e.name}: {x}' for x in f]
                except ValueError as ex:
                    failures.append(f'{e.name}: palette {ex}')
            elif e.tag == 'FCV':
                total += 1
                cam_total += e.is_camera
                face_total += e.is_face
                try:
                    if motion_round_trips(arc, e):
                        ok += 1
                    else:
                        failures.append(f'{e.name}: re-serialisation differs')
                except ValueError as ex:
                    failures.append(f'{e.name}: {ex}')
            elif e.tag == 'SEQ':
                if re.fullmatch(r'(\d{4}_)?op\d\d', arc.stem):
                    continue       # op/opNN.das "SEQ": the codec conversation blocks (ss_term.cpp term_ope_tbl), not MotionSeqKey tables
                seq_total += 1
                try:
                    if fcv.serialise_seq(fcv.parse_seq(e.data, e.endian), e.endian) == e.data:
                        seq_ok += 1
                    else:
                        failures.append(f'{e.name}: sequence re-serialisation differs')
                except ValueError as ex:
                    failures.append(f'{e.name}: sequence {ex}')
    # the character table against the source: every default attachment must load
    tab_total = tab_ok = 0
    for stem, table in character.TABLE.items():
        if src.get(stem) is None:
            continue
        for a in table:
            tab_total += 1
            try:
                mesh_source(src.entry(character.ref(a.bin, stem)), src.entry(character.ref(a.tpl, stem)), a.role)
                tab_ok += 1
            except MeshSourceError as e:
                failures.append(f'character.TABLE {stem} {a.role}: {e}')
    print(f'{len(arcs)} archives (' + ', '.join(f'{v} {k}' for k, v in sorted(kinds.items())) + f'): {total} motions '
          f'({cam_total} event camera motions, {face_total} event face shape tables), {ok} byte-identical round-trips; {seq_total} sequence tables, {seq_ok} byte-identical')
    if nested:
        print('  nested entries: ' + ', '.join(f'{v} in {k}' for k, v in sorted(nested.items())))
    if placeholders:
        print(f'  {placeholders} event TPL bins are 32-byte 0x20-filled placeholders (no palette)')
    if das_total:
        print(f'  {das_total} .das archives ({das_yz2} yz2-compressed): {das_ok} decompress to the header\'s size and parse as '
              f'consistent containers, {das_entries} entries (their FCV / SEQ / BIN / TPL are in the counts above)')
    print(f'  {bin_total} models, {bin_ok} byte-identical round-trips ({shaped} with a shape table, {shape_keys} shape keys); '
          f'{tpl_total} texture palettes, {tex_total} textures decoded, '
          f'{tex_lossless} lossless (I4 / IA8), {tex_ok} byte-identical re-encodings')
    if ps2_models:
        print(f'  {ps2_models} PS2 model / texture entries (another format, not read)')
    print(f'  character table: {tab_ok} of {tab_total} attachments load from this source')
    for f in failures:
        print(f'  FAIL {f}')
    status = 0 if not failures else 1
    if args.dump or args.dolphin:
        from motion import dolphin
        if args.dolphin:
            dumps = dolphin.capture(args.source[0], args.dolphin_iso, args.dump_out)
        else:
            dumps = [args.dump]
        players = [a for a in arcs if a.kind == 'hakase' and a.ext == '.drs']   # the dump names a PL_DATA_ADDR body offset
        for dump_path in dumps:
            status |= dolphin.compare(dump_path, players, variant='fma' if args.fma else 'plain', verbose=True)
            if args.fma_too:
                status |= dolphin.compare(dump_path, players, variant='fma', verbose=True)
    sys.exit(status)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('list')
    p.add_argument('source', nargs='+', help='archive file(s) or disc image(s); both discs may be given')
    p.add_argument('--character', help='leon / ashley / ada / hunk / krauser / wesker (or plNN): every motion that player can play, '
                                       'per archive, with the game function that plays it (player archive, melee via em10.drs, '
                                       'enemy / vehicle archives, weapon modules, rooms, room ETM files, events, sub screen)')
    p.add_argument('--all-sources', action='store_true', help='the inventory: per file, per tag, counts (nested ETM / EFF / SMD entries included)')
    p.set_defaults(func=cmd_list)
    p = sub.add_parser('export')
    p.add_argument('source', nargs='+', help='archive file(s) or disc image(s): a GameCube disc for the body of a PS2 motion')
    p.add_argument('--archive', help='archive name when the source is a disc (plNN.drs, em10.drs, rNNN.das, rNNNsMM.evd, ss_oc101.dat, '
                                     'the PS2 disc\'s NNNN_name.dat)')
    p.add_argument('--motion', help='entry index N, or the name of an event bin / ETM file (em1000_s00_000.fcv, pl00017.fcv)')
    p.add_argument('--all', action='store_true')
    p.add_argument('--model', help='model .bin file or [stem:]index (default: the character table\'s body of the '
                                   'motion\'s archive, else its entry 0); "pl00:0" takes the body from another archive')
    p.add_argument('--character', help='leon / ada / hunk / krauser / wesker (or plNN): play the motion on that '
                                       'player\'s body with the character table\'s attachments (= --model plNN:body)')
    p.add_argument('--tpl', type=lambda s: int(s, 0), help='texture palette entry of the body (default: the entry after the model)')
    p.add_argument('--mesh', action='append', metavar='[stem:]BIN[:[stem:]TPL]',
                   help='attachment model entry (head, hair, hands ...) skinned to the body parts, with its TPL entry '
                        '(default: the table\'s palette for a table entry, else BIN + 1); "wep04:6:13" takes the .bin from '
                        'another archive of the source; repeatable')
    p.add_argument('--body-only', action='store_true', help='no attachments from the character table')
    p.add_argument('--no-mesh', action='store_true', help='skeleton only (stick-figure placeholder mesh)')
    p.add_argument('--render-nice', metavar='DIR', help='with the Blender check: EEVEE renders with three area lights, the camera '
                                                       'framed on the animated character (and one per shape key) into DIR')
    p.add_argument('--strip', action='store_true', help='with --blender-check RENDER_DIR: also render every frame into a film strip PNG and an mp4')
    p.add_argument('-o', '--output', required=True)
    p.add_argument('--bvh')
    p.add_argument('--no-ik', action='store_true', help='skip the IK (raw keys on the parts)')
    p.add_argument('--no-root', action='store_true', help='no root motion track on the model node')
    p.add_argument('--fps', type=float, default=30.0)
    p.add_argument('--scale', type=float, default=0.001, help='units per game millimetre (default 0.001: metres)')
    p.add_argument('--fma', action='store_true', help='use the fused multiply-add helper build')
    p.add_argument('--blender-check', nargs='?', const='', metavar='RENDER_DIR',
                   help='import the result in headless Blender, compare bone positions, render 4 frames to RENDER_DIR')
    p.set_defaults(func=cmd_export)
    p = sub.add_parser('verify')
    p.add_argument('source', nargs='+', help='archive file(s) or disc image(s); both discs may be given')
    p.add_argument('--dump', help='Dolphin memory dump (tools/motion/dolphin.py capture) to compare poses against')
    p.add_argument('--dolphin', action='store_true', help='run the game in Dolphin and capture a dump first')
    p.add_argument('--dolphin-iso', default='orig/G4BE08/re4_debug_disc1.iso')
    p.add_argument('--dump-out', default='/tmp/mot/dolphin_dump.bin')
    p.add_argument('--fma', action='store_true')
    p.add_argument('--fma-too', action='store_true', help='also compare with the fused multiply-add helper build')
    p.set_defaults(func=cmd_verify)
    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
