"""MotionData ("FCV" archive entries) and sequence tables ("SEQ"): parse and byte-exact serialise.

Layout (big-endian on the GameCube, the same layout little-endian on the PS2 disc; from
game/motion.cpp MotionSetCore / HermiteInterpolation / Fcc_get_data_*):

  u16 maxFrame            last motion frame (the game plays frames 0..maxFrame, maxFrame+1 frames);
                          bits 14-15 are flags (MotionSetCore and cam_motion mask them: `& 0x3FFF`),
                          set on the event camera motions
  u8  nJoints
  u16 kind[nJoints]       bits 0-7: kind (1 root pos, 0x40 root rot, else &2 rot, &4 pos, &8 scale,
                          &0x30 rot), bits 8-11: attach camera channel, bits 12-15: Fcc key type
  u8  partsNo[nJoints]    model parts index per motion joint
  pad to 4
  u32 size                total size of the entry including the padding (MotionSetCore steps over
                          the word without reading it: `tbl++`); the archive entries carry the
                          entry size, the event camera motions (Evd/*.evd cam/*.fcv) a zero
  u32 keyOfs[nJoints]     offset of the joint's key block (relocated to a pointer at load time)
  key blocks, one per joint, each 3 axes (x, y, z) back to back:
      u16 n; u16 frame[n]; key[n]   with key = Fcc layout `type` (below)
  padding to 32 bytes: 0xCD in the ハカセ archives (the packer's uninitialised buffer), 0x00 in the
  event bins and the room ETM files (`fill`)

IF YOU ARE WRITING YOUR OWN IMPORTER, READ THIS: a joint whose kind has bit 0x10 or 0x20 set is an
IK chain root (IKInit: bits 8-11 of the kind word = bend axis, 0x20 = toe correction, 0x80 = 4-joint
chain), and the `pos` (kind & 4) keys on the chain's END EFFECTOR (ankles, hands) are NOT that joint's
local translation: they are the target position in MODEL space that game/ik.cpp InverseKinematics
aims the chain at every frame. Applying those keys as bone translations produces stretched or
folded limbs. A correct pose needs the IK solve (and the model's blend table for the double
joints), which is why this tool evaluates poses with the game's own code (tools/motion/host) instead
of reading the keys literally. The same is very likely true of the PC/UHD `.fcv` files.

The key blocks are contiguous in the file but NOT in joint order (the exporter's traversal order);
`Motion.layout` keeps that order so that the serialisation is byte-identical.

Fcc key layouts (Fcc_get_data_XYZ, type = X*4 + Y; s16 and s8 fields are value / 10000):
  type  value  in-tan  out-tan  size
  0     f32    f32     f32      12
  1     f32    s16     s16       8
  2     f32    s8      s8        6
  4     s16    f32     f32      10
  5     s16    s16     s16       6
  6     s16    s8      s8        4
  8     s8     f32     f32       9
  9     s8     s16     s16       5
  10    s8     s8      s8        3
  15    f32    -       -         4   (no tangents; not used by the motion data)
HermiteInterpolation(prm, out, hist): for the segment k0 <= frame < k1 the game evaluates
hermite({v[k0], v[k1]}, {out_tan[k0], in_tan[k1]}, (frame - f0) / (f1 - f0)).

Sequence table ("SEQ", MotionSetCore `seq`): u16 count, u8 flags (bit0: Mot_attr 0x1000, reverse
sequence), u8 pad, MotionSeqKey[count] {u16 frame (10.6 fixed), u8 Se, u8 Free}, 0xCD padding.
"""
import struct
from dataclasses import dataclass, field

FILL = 0xCD
ALIGN = 0x20

# type -> (value fmt, tangent fmt); fmt: 'f' f32, 'h' s16, 'b' s8
FCC_FMT = {
    0: ('f', 'f'), 1: ('f', 'h'), 2: ('f', 'b'),
    4: ('h', 'f'), 5: ('h', 'h'), 6: ('h', 'b'),
    8: ('b', 'f'), 9: ('b', 'h'), 10: ('b', 'b'),
    15: ('f', None),
}
FMT_SIZE = {'f': 4, 'h': 2, 'b': 1}

KIND_ROOT_POS = 1
KIND_ROOT_ROT = 0x40


def fcc_key_size(t):
    v, tn = FCC_FMT[t]
    return FMT_SIZE[v] + (2 * FMT_SIZE[tn] if tn else 0)


def fcc_struct(t, endian='>'):
    if t not in FCC_FMT:
        raise ValueError(f'Fcc key type {t}: no Fcc_get_data_* reader for it')
    v, tn = FCC_FMT[t]
    return struct.Struct(endian + v + (tn * 2 if tn else ''))


def to_float(fmt, raw):
    """Raw field -> the value the game's Fcc_get_data_* produces (s16/s8 are 1/10000 units)."""
    return raw if fmt == 'f' else raw * 0.0001


@dataclass
class Axis:
    frames: list          # u16 frame numbers, one per key
    keys: list            # per key: (value, in_tan, out_tan) raw fields (f32 as float, s16/s8 as int)


@dataclass
class Joint:
    kind: int             # low byte of kind[] word
    channel: int          # bits 8-11
    fcc_type: int         # bits 12-15
    parts_no: int
    axes: list = field(default_factory=list)   # 3 Axis

    @property
    def info(self):
        return self.kind | (self.channel << 8) | (self.fcc_type << 12)

    def is_root_pos(self):
        return self.kind == KIND_ROOT_POS

    def is_root_rot(self):
        return self.kind == KIND_ROOT_ROT

    def target(self):
        """'rot' / 'pos' / 'scale' / None following MotionMoveCore's kind tests (in that order)."""
        if self.kind == KIND_ROOT_POS or self.kind == KIND_ROOT_ROT:
            return None
        if self.kind & 2:
            return 'rot'
        if self.kind & 4:
            return 'pos'
        if self.kind & 8:
            return 'scale'
        if self.kind & 0x30:
            return 'rot'
        return None

    def block_size(self):
        ks = fcc_key_size(self.fcc_type)
        return sum(2 + 2 * len(a.frames) + ks * len(a.frames) for a in self.axes)


@dataclass
class Motion:
    max_frame: int
    joints: list
    layout: list          # joint indices in file (key block) order
    zero_size: bool = False   # empty-motion variant with a zero size word (see parse)
    fill: int = FILL      # padding byte: 0xCD (archives) or 0x00 (event bins, ETM files)
    size_word: int = None     # the size word when it is not the entry size (0 in the event cameras)
    frame_flags: int = 0      # maxFrame bits 14-15

    @property
    def n_frames(self):
        return self.max_frame + 1


def header_size(n):
    return ((3 + 3 * n + 3) & ~3) + 4 + 4 * n


def _fill_of(tail):
    """The padding byte of a run of identical 0xCD or 0x00 bytes, else None."""
    if not tail:
        return FILL
    if tail in (bytes([FILL]) * len(tail), b'\0' * len(tail)):
        return tail[0]
    return None


def parse(d: bytes, endian='>') -> Motion:
    raw_max_frame, n = struct.unpack(endian + 'HB', d[:3])
    max_frame, frame_flags = raw_max_frame & 0x3FFF, raw_max_frame >> 14
    if n == 0:
        # No joints: header, pad byte, size word (0x20), padding. One archive variant has a zero
        # size word followed by zero bytes up to 16 (`zero_size`).
        size, = struct.unpack(endian + 'I', d[4:8])
        if d[3] != 0 or len(d) != ALIGN:
            raise ValueError('empty motion: bad pad byte or size')
        if size == 0 and d[8:16] == b'\0' * 8 and d[16:] == bytes([FILL]) * 16:
            return Motion(max_frame, [], [], zero_size=True, frame_flags=frame_flags)
        fill = _fill_of(d[8:])
        if fill is None:
            raise ValueError('empty motion: unexpected bytes after the header')
        return Motion(max_frame, [], [], fill=fill, size_word=None if size == ALIGN else size, frame_flags=frame_flags)
    infos = struct.unpack(f'{endian}{n}H', d[3:3 + 2 * n])
    parts_no = d[3 + 2 * n:3 + 3 * n]
    o = (3 + 3 * n + 3) & ~3
    size, = struct.unpack(endian + 'I', d[o:o + 4])
    o += 4
    key_ofs = struct.unpack(f'{endian}{n}I', d[o:o + 4 * n])
    o += 4 * n
    joints = []
    ends = []
    for i in range(n):
        info = infos[i]
        j = Joint(info & 0xFF, (info >> 8) & 0xF, info >> 12, parts_no[i])
        st = fcc_struct(j.fcc_type, endian)
        ks = st.size
        p = key_ofs[i]
        if p + 6 > len(d):
            raise ValueError(f'joint {i} (kind {info:#06x}, parts {parts_no[i]}) key block offset {p:#x} is at or past the end')
        for _ in range(3):
            if p + 2 > len(d) - ALIGN + 1 and d[p:p + 2] == bytes([FILL]) * 2:
                raise ValueError(f'joint {i} (kind {info:#06x}, parts {parts_no[i]}) key block at {key_ofs[i]:#x} lies in the 0xCD padding')
            k, = struct.unpack(endian + 'H', d[p:p + 2])
            if p + 2 + 2 * k + ks * k > len(d):
                raise ValueError(f'joint {i} (kind {info:#06x}, parts {parts_no[i]}) axis with {k} keys at {p:#x} runs past the end')
            frames = list(struct.unpack(f'{endian}{k}H', d[p + 2:p + 2 + 2 * k]))
            p += 2 + 2 * k
            keys = [st.unpack_from(d, p + ks * m) for m in range(k)]
            p += ks * k
            j.axes.append(Axis(frames, keys))
        joints.append(j)
        ends.append(p)
    layout = sorted(range(n), key=lambda i: key_ofs[i])
    # Blocks must be contiguous from the header to the end (a type-15 block, f32 values without
    # tangents: the event cameras, starts 4-aligned over zero bytes), then padding to 32 bytes.
    p = o
    for i in layout:
        if joints[i].fcc_type == 15:
            q = (p + 3) & ~3
            if d[p:q] != b'\0' * (q - p):
                raise ValueError(f'joint {i} key block alignment bytes at {p:#x} are not zero')
            p = q
        if key_ofs[i] != p:
            raise ValueError(f'joint {i} key block at {key_ofs[i]:#x}, expected {p:#x}')
        p = ends[i]
    pad = len(d) - p
    fill = _fill_of(d[p:]) if 0 <= pad < ALIGN else None
    if fill is None:
        raise ValueError(f'trailing bytes at {p:#x} are not 0xCD / 0x00 padding to 32')
    return Motion(max_frame, joints, layout, fill=fill, size_word=None if size == len(d) else size, frame_flags=frame_flags)


def serialise(m: Motion, endian='>') -> bytes:
    """The motion's bytes. endian '<' gives the host image (every u16/f32/s16 field byte-swapped,
    same layout) the native helper evaluates with the game's byte-wise readers."""
    n = len(m.joints)
    raw_max_frame = m.max_frame | (m.frame_flags << 14)
    if n == 0:
        if m.zero_size:
            return b'\0' * 16 + bytes([FILL]) * 16
        size = ALIGN if m.size_word is None else m.size_word
        return struct.pack(endian + 'HBBI', raw_max_frame, 0, 0, size) + bytes([m.fill]) * (ALIGN - 8)
    out = bytearray(struct.pack(endian + 'HB', raw_max_frame, n))
    out += struct.pack(f'{endian}{n}H', *(j.info for j in m.joints))
    out += bytes(j.parts_no for j in m.joints)
    out += b'\0' * ((-len(out)) & 3)
    hdr = len(out) + 4 + 4 * n
    ofs = [0] * n
    p = hdr
    blocks = []
    for i in m.layout:
        j = m.joints[i]
        b = bytearray()
        if j.fcc_type == 15:
            b += b'\0' * (((p + 3) & ~3) - p)
        ofs[i] = p + len(b)
        st = fcc_struct(j.fcc_type, endian)
        for a in j.axes:
            b += struct.pack(f'{endian}H{len(a.frames)}H', len(a.frames), *a.frames)
            for k in a.keys:
                b += st.pack(*k)
        blocks.append(bytes(b))
        p += len(b)
    total = (p + ALIGN - 1) & ~(ALIGN - 1)
    out += struct.pack(endian + 'I', total if m.size_word is None else m.size_word)
    out += struct.pack(f'{endian}{n}I', *ofs)
    for b in blocks:
        out += b
    out += bytes([m.fill]) * (total - p)
    return bytes(out)


@dataclass
class SeqKey:
    frame: int   # 10.6 fixed point motion frame
    se: int
    free: int

    @property
    def frame_f(self):
        return (self.frame >> 6) + (self.frame & 0x3F) * 0.015625


@dataclass
class Sequence:
    flags: int
    keys: list
    fill: int = FILL      # padding byte: 0xCD (archives) or 0x00 (ETM .seq files)


def parse_seq(d: bytes, endian='>') -> Sequence:
    count, flags, pad = struct.unpack(endian + 'HBB', d[:4])
    if pad != 0:
        raise ValueError('sequence pad byte not zero')
    keys = [SeqKey(*struct.unpack(endian + 'HBB', d[4 + 4 * i:8 + 4 * i])) for i in range(count)]
    p = 4 + 4 * count
    tail = len(d) - p
    fill = _fill_of(d[p:]) if 0 <= tail < ALIGN else None
    if fill is None:
        raise ValueError(f'sequence trailing bytes at {p:#x} are not 0xCD / 0x00 padding')
    return Sequence(flags, keys, fill)


def serialise_seq(s: Sequence, endian='>') -> bytes:
    out = bytearray(struct.pack(endian + 'HBB', len(s.keys), s.flags, 0))
    for k in s.keys:
        out += struct.pack(endian + 'HBB', k.frame, k.se, k.free)
    total = (len(out) + ALIGN - 1) & ~(ALIGN - 1)
    out += bytes([s.fill]) * (total - len(out))
    return bytes(out)
