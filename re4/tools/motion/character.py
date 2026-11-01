"""Which attachment models make up a character: the game's model set-up code, per archive.

The body `.bin` of a character archive is entry 0 (PL_ARC 4) with its palette in entry 1 (PL_ARC 5);
the head, hair, eyes, hands ... are separate `.bin`s that the character's set-up code hangs on the
same parts (ModInfoMgr.create(bin, tpl) + addModel). The table below is read off those functions:
the players' `setModel` / `setRightHand` / `setLeftHand` (what they load before the weapon module
runs: the default game state) and the Ganado's `em10ModelInit` (`em10_set.cpp` fills mot[] for the
model type, `em10HeadSet(0)` / `em10HandSet(0)` pick the normal head and the relaxed hands).
Entry indices are the archive's (the game's PL_ARC index minus 4: `archive.ARC_INDEX_BASE`).

A cross-archive reference is written 'stem:entry' (the weapon-grip hands of the weapon modules,
`cPlBody::initWepHand(WEP_ARC_PTR(0xA))` + `setRightHand(1)`, are a wepNN.drs `.bin` drawn with the
player's hand palette; the default handgun modules wep01 / wep02 do not touch the hands, so the
defaults below are all in-archive). The table is checked against the disc by `verify`.

The second half answers "which motions can this player play, and what plays them": PLAYER_TYPE
(read.cpp's pl_type, weapon table and EmFileTbl variant per archive), SS_MOTIONS (the sub screen's
motions on the player model) and the queries over refs.py (generated from src/ by gen_refs.py:
every MotionSetCore call with the archive entry it plays): the player archive's referenced entries,
the enemy / vehicle archives played on the player, the weapon modules' entries, the rooms'.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Attachment:
    bin: object      # entry index, or 'stem:entry' in another archive
    tpl: object
    role: str
    source: str      # the game function the pair comes from


def A(bin, tpl, role, source):
    return Attachment(bin, tpl, role, source)


# cPlLeon::setModel (game/pl_leon.cpp): body 4/5, costume extras 0xA/5 (costume 0..3), face 0xD/5
# (Body->pFace), head 8/7 (Body->pShape / pHeadData: the shape table), hair 6/7 (Body->pHair),
# eyes 9/7 (Body->pEye, be_flag 0x40), then setRightHand(0) = 0x12/0x11 and setLeftHand(1) = 0x15/0x11.
# The game poses the eyelid / eye parts (0x1C, 0x20, 0x21: cPlayer::moveEyeNormal) by code, not by
# the motion; they are skeleton parts, so the eye models are bound through the skin like the rest.
LEON = [
    A(0, 1, 'body', 'cPlLeon::setModel: modelInit(PL_ARC 4, 5)'),
    A(6, 1, 'costume', 'cPlLeon::setModel: create(PL_ARC 0xA, 5), pl_costume 0..3'),
    A(9, 1, 'face', 'cPlLeon::setModel: create(PL_ARC 0xD, 5) -> Body->pFace'),
    A(4, 3, 'head', 'cPlLeon::setModel: create(PL_ARC 8, 7) -> Body->pShape, pHeadData'),
    A(2, 3, 'hair', 'cPlLeon::setModel: create(PL_ARC 6, 7) -> Body->pHair'),
    A(5, 3, 'eyes', 'cPlLeon::setModel: create(PL_ARC 9, 7) -> Body->pEye'),
    A(14, 13, 'right hand', 'cPlLeon::setRightHand(0): create(PL_ARC 0x12, 0x11)'),
    A(17, 13, 'left hand', 'cPlLeon::setLeftHand(1): create(PL_ARC 0x15, 0x11)'),
]

# cPlAshley::setModel (game/pl_ashley.cpp): body 4/5, face 7/9 (Body->pShape / pHeadData), hair
# 6/0xB, skirt 8/5 (be_flag 0x40), 0xA/5, setRightHand(0) = 0x11/5, setLeftHand(0) = 0x14/5.
ASHLEY = [
    A(0, 1, 'body', 'cPlAshley::setModel: modelInit(PL_ARC 4, 5)'),
    A(3, 5, 'head', 'cPlAshley::setModel: create(PL_ARC 7, 9) -> Body->pShape, pHeadData'),
    A(2, 7, 'hair', 'cPlAshley::setModel: create(PL_ARC 6, 0xB)'),
    A(4, 1, 'skirt', 'cPlAshley::setModel: create(PL_ARC 8, 5), be_flag 0x40'),
    A(6, 1, 'accessory', 'cPlAshley::setModel: create(PL_ARC 0xA, 5)'),
    A(13, 1, 'right hand', 'cPlAshley::setRightHand(0): create(PL_ARC 0x11, 5)'),
    A(16, 1, 'left hand', 'cPlAshley::setLeftHand(0): create(PL_ARC 0x14, 5)'),
]

# cPlAda::setModel (pl02/pl02.cpp): body 4/5, hair 6/7 (Body->pHair), head 8/7 (Body->pShape /
# pHeadData), eyes 9/0xA (be_flag 0x40), setRightHand(0) = 0x11/5, setLeftHand(0) = 0x12/5.
# pl0c.drs is the archive laid out for this code (entry 4: 1104-vertex head with a shape table,
# entries 13 / 14: hands using texture 6 of the 7-texture body palette). pl02.drs is the event Ada
# (red dress; events attach parts by name from their scripts, Event::ExePacket_SetParts): her body
# .bin has the hands modelled in, entry 13 is empty, entry 14 wants texture 6 of a 5-texture
# palette, and entry 4 is a 29-vertex stub without a shape table, rigged to a 67-part skeleton that
# is not the body's (its one weight names parts 7, the body's left upper arm, so it floats beside
# the shoulder in the game's own skinning). pl02's default is therefore body, hair and eyes/face.
ADA = [
    A(0, 1, 'body', 'cPlAda::setModel: modelInit(PL_ARC 4, 5)'),
    A(2, 3, 'hair', 'cPlAda::setModel: create(PL_ARC 6, 7) -> Body->pHair'),
    A(4, 3, 'head', 'cPlAda::setModel: create(PL_ARC 8, 7) -> Body->pShape, pHeadData'),
    A(5, 6, 'eyes', 'cPlAda::setModel: create(PL_ARC 9, 0xA), be_flag 0x40'),
    A(13, 1, 'right hand', 'cPlAda::setRightHand(0): create(PL_ARC 0x11, 5)'),
    A(14, 1, 'left hand', 'cPlAda::setLeftHand(0): create(PL_ARC 0x12, 5)'),
]
ADA_EVENT = [a for a in ADA if a.role in ('body', 'hair', 'eyes')]

# cPlWesker::setModel (pl0d/pl_wesker.cpp): body 4/5, extra 0xA/5, head 8/7 (Body->pShape), hair
# 6/7 (Body->pHair), setRightHand(0) = 0x12/0x11, setLeftHand(0) = 0x14/0x11.
WESKER = [
    A(0, 1, 'body', 'cPlWesker::setModel: modelInit(PL_ARC 4, 5)'),
    A(6, 1, 'costume', 'cPlWesker::setModel: create(PL_ARC 0xA, 5)'),
    A(4, 3, 'head', 'cPlWesker::setModel: create(PL_ARC 8, 7) -> Body->pShape, pHeadData'),
    A(2, 3, 'hair', 'cPlWesker::setModel: create(PL_ARC 6, 7) -> Body->pHair'),
    A(14, 13, 'right hand', 'cPlWesker::setRightHand(0): create(PL_ARC 0x12, 0x11)'),
    A(16, 13, 'left hand', 'cPlWesker::setLeftHand(0): create(PL_ARC 0x14, 0x11)'),
]

# cPlHunk::setModel (pl06/pl06.cpp): body 4/5, mask 6/7 (Body->pHair), setRightHand(0) = 0x12/0x11,
# setLeftHand(1) = 0x15/0x11.
HUNK = [
    A(0, 1, 'body', 'cPlHunk::setModel: modelInit(PL_ARC 4, 5)'),
    A(2, 3, 'mask', 'cPlHunk::setModel: create(PL_ARC 6, 7) -> Body->pHair'),
    A(14, 13, 'right hand', 'cPlHunk::setRightHand(0): create(PL_ARC 0x12, 0x11)'),
    A(17, 13, 'left hand', 'cPlHunk::setLeftHand(1): create(PL_ARC 0x15, 0x11)'),
]

# cPlKlauser::setModel (pl0a/pl_klauser.cpp): body 4/5, 6/7, 8/9 (be_flag 0x20), 0xA/0xB (hidden:
# be_flag &= ~8), 0xE/9, 0xF/0x10, glow 0x18/0x19 (hidden, tex-render), setRightHand(0) = 0x12/0x11,
# setLeftHand(1) = 0x14/0x11. The two hidden models are not part of the visible default.
KRAUSER = [
    A(0, 1, 'body', 'cPlKlauser::setModel: modelInit(PL_ARC 4, 5)'),
    A(2, 3, 'hair', 'cPlKlauser::setModel: create(PL_ARC 6, 7)'),
    A(4, 5, 'head', 'cPlKlauser::setModel: create(PL_ARC 8, 9), be_flag 0x20'),
    A(10, 5, 'face', 'cPlKlauser::setModel: create(PL_ARC 0xE, 9)'),
    A(11, 12, 'accessory', 'cPlKlauser::setModel: create(PL_ARC 0xF, 0x10)'),
    A(14, 13, 'right hand', 'cPlKlauser::setRightHand(0): create(PL_ARC 0x12, 0x11)'),
    A(16, 13, 'left hand', 'cPlKlauser::setLeftHand(1): create(PL_ARC 0x14, 0x11)'),
]

# em10ModelInit (em10/em10.cpp) with Em10Set model type 0 (em10/em10_set.cpp, the male villager):
# modelInit(mot[1] = ARC 0x1BC, mot[0] = ARC 0x1BD); em10HeadSet(0): create(mot[2] = ARC 0x1BE,
# mot[5] = ARC 0x1BD); em10HandSet(0): right create(mot[6] = ARC 0x1C0, mot[0]), left
# create(mot[11] = ARC 0x1C5, mot[0]). Types 1 / 3 / 4 swap the body and head (ARC 0x1D8.., 0x1DC..,
# 0x1E0..) and keep the hands; accessories (hats, sacks, the weapon) depend on the cEm flags.
GANADO_VILLAGE = [
    A(440, 441, 'body', 'em10ModelInit: modelInit(mot[1] = ARC 0x1BC, mot[0] = ARC 0x1BD), Em10Set type 0'),
    A(442, 441, 'head', 'em10HeadSet(0): create(mot[2] = ARC 0x1BE, mot[5] = ARC 0x1BD)'),
    A(444, 441, 'right hand', 'em10HandSet(0): create(mot[6] = ARC 0x1C0, mot[0] = ARC 0x1BD)'),
    A(449, 441, 'left hand', 'em10HandSet(0): create(mot[11] = ARC 0x1C5, mot[0] = ARC 0x1BD)'),
]

TABLE = {
    'pl00': LEON,
    'pl01': ASHLEY,
    'pl02': ADA_EVENT,
    'pl0c': ADA,
    'pl06': HUNK,
    'pl0a': KRAUSER,
    'pl0d': WESKER,
    'em10': GANADO_VILLAGE,
}

# What plays the head's shape keys: the ShapeData entries (tagged 'FCV' like the motions: u16 nFrame,
# u8 num channels, u16 flags[num], u8 shape index[num], Hermite key tables) that setFace hands to
# ShapeSet. archive -> {shape table index: the call}. The game has no names for the shapes;
# Ashley's (pl01, two shapes) are played by the events (Event::ExePacket ShapeSet) - cPlAshley::setFace
# is empty - and Wesker's setFace names 0x62 / 0x63 but his head has no shape table.
FACES = {
    'pl00': {0: 'cPlLeon::setFace(1): PL_ARC 0x62 (pain)', 1: 'cPlLeon::setFace(2): PL_ARC 0x63'},
    'pl0c': {1: 'cPlAda::setFace(1): PL_ARC 0x62', 0: 'cPlAda::setFace(2): PL_ARC 0x63'},
}



@dataclass(frozen=True)
class Melee:
    archive: str     # stem of the archive the game reads the motion from ('em10', or the player's own)
    entry: int       # entry index (PL_ARC - 4)
    seq: object      # SEQ entry index when MotionSetCore is given one, else None
    role: str
    source: str      # the game routine


ARC_INDEX_BASE = 4


def M(archive, arc_no, role, source, seq=None):
    """Table entry by the game's PL_ARC index (entry index = PL_ARC - 4)."""
    return Melee(archive, arc_no - ARC_INDEX_BASE, None if seq is None else seq - ARC_INDEX_BASE, role, source)


# The player's melee motions come from TWO archives. The routines in em10/em10.cpp (plem10Kick,
# plem10Kick2, plem10FS, plem10KneeKick, plem10NeckBreak, plem10Showtay) start with
# `pl->subArc = em->subArc`: the caught Ganado's archive (em10.drs; every em1x militia archive carries
# the same bytes at these entries), and index it with PL_ARC_PTR(pl->subArc, N); only the kneeling
# kick is PL_ARC_PTR(pG->pPlayer, 0x25) in the player's own archive. `cPlayer::cPlayer` sets subArc
# to PL_DATA_ADDR (= pG->pPlayer) and every routine restores `pl->subArc = pl->subArc2` on exit.
# Two prompts (em10.cpp, the ActBtn.set block before em10KickAction): on a kneeling Ganado (Be_flg
# 0x40000000) em10KneeDownAction sets r_no_3 = 1 and plem10Kick plays the player's own 0x25 (Leon
# ACT_KICK, Ada ACT_BACKKICK, Wesker ACT_NERICHAGI); on a stunned standing Ganado em10KickAction runs
# plem10Kick with r_no_3 = 0 (SetPlDamage -> PlSetRoutine(4, 0, 0, 0)) and plays the enemy archive's
# 0x29D (Leon ACT_KICK, Ada ACT_SENPUU "whirlwind kick"). `pl->r_no_3 = Rnd() & 3` after the pick
# only chooses the kick camera. The 0x29D bytes are the same for every player: on this disc Ada's
# whirlwind kick and Leon's roundhouse are one motion. 0x25 differs per player archive (pl0c's is
# Ada's own; pl00/pl0a/pl0d share one). pl_type picks the routine: 0 Leon / 2 Ada plem10Kick +
# suplex; 3 HUNK plem10Kick(r_no_3 = 1) + neck break (ACT_EXECUTE: Dm_NeckBreak -> EmCatchPLSet
# plem10NeckBreak) + suplex; 4 Krauser plem10Kick2 + knee kick; 5 Wesker plem10Showtay (ACT_PALM_SHOCK)
# + plem10Kick(r_no_3 = 1) + suplex.
KICK_OWN = 'kick on a kneeling enemy (Leon KICK / Ada BACKKICK / Wesker NERICHAGI)'
_KICK = [
    M(None, 0x25, KICK_OWN, 'em10KneeDownAction -> plem10Kick r_no_3 = 1: PL_ARC_PTR(pG->pPlayer, 0x25)'),
    M('em10', 0x29D, 'kick on a stunned enemy (Leon KICK / Ada SENPUU; same bytes in every enemy archive)', 'em10KickAction -> plem10Kick r_no_3 = 0: PL_ARC_PTR(pl->subArc = em->subArc, 0x29D)'),
]
_SUPLEX = [M('em10', 0xD6, 'suplex', 'plem10FS: PL_ARC_PTR(pl->subArc, 0xD6) (em10FSAction, pl_type != 4)')]
MELEE = {
    'pl00': _KICK + _SUPLEX,
    'pl0b': _KICK + _SUPLEX,
    'pl0c': _KICK + _SUPLEX,
    'pl06': [_KICK[0]] + _SUPLEX + [M('em10', 0x2B9, 'neck break', 'plem10NeckBreak: PL_ARC_PTR(pl->subArc, 0x2B9) (em10KickAction pl_type 3 -> Dm_NeckBreak)')],
    'pl0a': [M('em10', 0x29D, 'kick', 'plem10Kick2: PL_ARC_PTR(pl->subArc, 0x29D) + SEQ 0x29E (pl_type 4)', seq=0x29E),
             M('em10', 0x2B4, 'knee kick', 'plem10KneeKick: PL_ARC_PTR(pl->subArc, 0x2B4) (em10FSAction pl_type 4)')],
    'pl0d': [_KICK[0]] + _SUPLEX + [M('em10', 0x2B4, 'palm strike', 'plem10Showtay: PL_ARC_PTR(pl->subArc, 0x2B4) (em10KickAction pl_type 5)')],
}

# --character names -> the player archive stem (the game's pl_type and costume: ReadPlayerData).
CHARACTERS = {
    'leon': 'pl00',
    'ashley': 'pl01',
    'ada': 'pl0c',
    'hunk': 'pl06',
    'krauser': 'pl0a',
    'wesker': 'pl0d',
}

# player archive stem -> (pl_type, weapon table of read.cpp, the player's own code module directory
# under src/ whose PL_ARC references apply to this player only, the EmFileTbl variant of read.cpp)
PLAYER_TYPE = {
    'pl00': (0, 'wep_data_leon', 'game', 'EmFileTbl'),
    'pl08': (0, 'wep_data_leon', 'game', 'EmFileTbl'),
    'pl09': (0, 'wep_data_leon', 'game', 'EmFileTbl'),
    'pl10': (0, 'wep_data_leon', 'game', 'EmFileTbl'),
    'pl01': (1, None, 'game', 'EmFileTbl'),
    'pl05': (1, None, 'game', 'EmFileTbl'),
    'pl0b': (2, 'wep_data_ada', 'pl02', 'EmFileTbl_Ada'),
    'pl0c': (2, 'wep_data_ada', 'pl02', 'EmFileTbl_Ada'),
    'pl06': (3, 'wep_data_hunk', 'pl06', 'EmFileTbl'),
    'pl0a': (4, 'wep_data_klauser', 'pl0a', 'EmFileTbl_Klauser'),
    'pl0d': (5, 'wep_data_wesker', 'pl0d', 'EmFileTbl_Wesker'),
}

# The sub screen motions played on a player's model (Sscrn/ss_model.cpp, ss_term.cpp): the codec
# screen's talking player (SS_ARC_PTR(d, 12) of the partner data file, d = SS/cmn/ss_ocNNN.dat,
# termMotionSet; 13 is its ShapeData), the cancel idle (ss_term.dat 14, termMotionCancel), Ashley's
# inventory idle (ss_cmmn.dat 22, ashleyModelInit). SS_ARC_PTR(arc, n) = arc->ofs[n] + arc with the
# file's four header words as ofs[0..3], so n is a PL_ARC-style index (entry n - 4). The player
# model there is built from the player archive (PL_ARC(4)..), so the motions target the same skeleton.
SS_MOTIONS = {
    'pl00': [('ss_oc*.dat', 12, 'termMotionSet: SS_ARC_PTR(d, 12) on MapMgr.getWork(0), the player of the codec call'),
             ('ss_term.dat', 14, 'termMotionCancel: SS_ARC_PTR(wk->pTerm, 14)')],
    'pl01': [('ss_cmmn.dat', 22, 'ashleyModelInit: SS_ARC_PTR(wk->pCmmn, 22)')],
}
SS_MOTIONS['pl08'] = SS_MOTIONS['pl09'] = SS_MOTIONS['pl10'] = SS_MOTIONS['pl00']


def attachments(stem):
    """The character's model list for an archive stem ('pl00'), body first; None when unknown."""
    return TABLE.get(stem)


# ---- every motion a player can play: the call sites of refs.py (gen_refs.py) sorted by archive ----

def _fmt(r):
    """'function (file:line)' of a reference, with the field it went through when it did."""
    s = f'{r["function"]} ({r["file"]}:{r["line"]})'
    if r.get('via'):
        s += f' via {r["via"]} = {r["fill"]}'
    if r.get('seq') is not None:
        s += f' + SEQ {r["seq"] + ARC_INDEX_BASE:#x}'
    return s


def _applies(r, stem):
    """A reference from a player module directory (pl0a/, pl0d/, pl02/, pl06/) applies to that player
    only; everything else (game/, em*/, wep*/, st*/) to every player."""
    mod = r['file'].split('/')[0]
    if mod in ('pl0a', 'pl0d', 'pl02', 'pl06'):
        return mod == PLAYER_TYPE[stem][2]
    return True


def player_archive_refs(stem):
    """{PL_ARC index: [call description]}: the player-archive entries the code plays
    (PL_ARC_PTR(pG->pPlayer, n), pl_mod.h PL_ARC(n), and pl->subArc outside the grab routines)."""
    import refs
    out = {}
    for r in refs.REFS:
        if r['class'] in ('player', 'sub') and _applies(r, stem):
            tag = _fmt(r) + (' [pl->subArc]' if r['class'] == 'sub' else '')
            out.setdefault(r['index'], []).append(tag)
    return out


def enemy_archive_refs_on_player(stem):
    """{enemy archive stem: {PL_ARC index: [call]}}: motions of enemy / vehicle / partner archives the
    game plays on the PLAYER model (the grab, kick, ride and escape routines: pl->subArc = em->subArc,
    PL_ARC_PTR(em->subArc, n) with the player as the cModel). Ada's enemy variants (EmFileTbl_Ada:
    em16 -> em46 ...) are mapped through read.cpp's tables."""
    import refs
    base, variant = refs.EM_FILES['EmFileTbl'], refs.EM_FILES[PLAYER_TYPE[stem][3]]
    remap = {b: v for b, v in zip(base, variant) if b and v and b != v}
    out = {}
    for r in refs.REFS:
        if r['class'] == 'em' and r['model'] == 'player' and r['stem'] and _applies(r, stem):
            arc = remap.get(r['stem'], r['stem'])
            out.setdefault(arc, {}).setdefault(r['index'], []).append(_fmt(r))
    return out


def weapon_archives(stem):
    """[(weapon module stem, [weapon numbers])] the player can load (read.cpp ReadWepData tables)."""
    import refs
    table = PLAYER_TYPE[stem][1]
    if table is None:
        return []
    by = {}
    for no, arc in enumerate(refs.WEP_FILES[table]):
        if arc:
            by.setdefault(arc, []).append(no)
    return sorted(by.items())


def weapon_archive_refs(wep):
    """{WEP_ARC index: [call]} for a weapon module archive: WEP_ARC_PTR(n) in the module's own
    sources and the shared player routines linked into it (modules.py UNITS)."""
    import refs
    files = set(refs.WEP_UNITS.get(wep, [f'{wep}/{wep}.cpp']))
    out = {}
    for r in refs.REFS:
        if r['class'] != 'wep':
            continue
        src_file = r['fill'].rsplit(':', 1)[0] if r.get('fill') else r['file']
        if r['stem'] == wep or (r['stem'] is None and (src_file in files or src_file.startswith(wep + '/'))):
            out.setdefault(r['index'], []).append(_fmt(r))
    return out


def room_refs_on_player():
    """{room stem: {ROOM_ARC index: [call]}}: room-archive motions the room scripts play on the
    player (pPL->motionSet(ROOM_ARC_PTR(..)), MotionSetCore(pPL, ..), PlRegistMotion -> m_MotTbl2)."""
    import refs
    out = {}
    for r in refs.REFS:
        if r['class'] == 'room' and r['model'] == 'player' and r['stem']:
            out.setdefault(r['stem'], {}).setdefault(r['index'], []).append(_fmt(r))
    return out


def unresolved_calls():
    """The motion-setting calls whose data pointer gen_refs.py could not tie to a constant archive
    entry (event bins, tables walked by index, work fields filled at run time)."""
    import refs
    return refs.UNRESOLVED


def melee(stem):
    """[(archive stem, Melee)] of the player's melee motions; the archive is the player's own when
    the table says None. Empty for a non-player archive."""
    return [(m.archive or stem, m) for m in MELEE.get(stem, [])]


def character_stem(name):
    """'leon' / 'pl00' -> 'pl00'."""
    name = name.lower()
    if name in CHARACTERS:
        return CHARACTERS[name]
    if name in TABLE or name in MELEE:
        return name
    raise ValueError(f'{name}: not a character ({", ".join(CHARACTERS)}) or a player archive stem')


def parse_ref(text, default_stem):
    """'12' -> (default_stem, 12); 'wep04:6' -> ('wep04', 6)."""
    if ':' in text:
        stem, idx = text.rsplit(':', 1)
        return stem, int(idx, 0)
    return default_stem, int(text, 0)


def ref(value, default_stem):
    """Table entry (int or 'stem:entry') -> (stem, entry)."""
    if isinstance(value, int):
        return default_stem, value
    return parse_ref(value, default_stem)
