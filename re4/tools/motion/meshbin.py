"""Model .bin ("BIN" archive entries, game/model.cpp ModelData) mesh data: parse and byte-exact serialise.

The file is one ModelData header followed by 32-byte aligned sections whose offsets the header
holds (game/model.cpp calcModelAddr turns them into pointers: pHead, pClr, pTex, pWeight, pParts,
vtxOrig, nrmOrig, blendTbl, flipTbl). On the disc the sections always come in this order, each
zero-padded to 32 bytes: parts records, vertices, normals, [shape table], colours, texture
coordinates, weights, display-list parts, [blend table], flip table (0xCD padded, last; the event
bins' models are padded with 0x00: `Mesh.fill`).

ModelData (include/model.h; 0x48 bytes for version 0x20030818, 0x40 for 0x20010801 which has no
blend / flip table words):
  u32 pHead, u32 0, u32 x8 (0x50 in version 0x20030818 files, 0 in the old ones; the game does not
  read it), u32 pClr, u32 pTex, u32 pWeight, u8 weight_palette_num, u8 nParts,
  u16 displist_num, u32 pParts, u32 flags, u32 nTex, u8 shift, u8 pad, u16 weight_ext_num,
  u32 shapeOfs, u32 vtxOrig, u32 nrmOrig, u16 nVtx, u16 nNrm, u32 version, [u32 blendTbl, u32 flipTbl]

What the game does with each array (game/trans.cpp commonModelTrans, the GX vertex descriptor
of the models; commonScreenMatSub / CalcSk1_x, the skinning; dbmodule.cpp DrawObjWireframe):
  vertices   nVtx x {s16 x, y, z, s16 matrix index}: GXSetVtxAttrFmt(POS, XYZ, S16, frac = shift),
             i.e. position = value / (1 << shift) millimetres (DrawObjWireframe: 1.0f / (1 << shift)).
             The matrix index selects the skinning matrix (below); the unskinned draw path
             (GXSetArray(POS, vtxOrig, 8)) strides over it.
  normals    nNrm x {s8 x, y, z, u8 matrix index} when flags bit29 (GX_S8 normals, 1.6 fixed
             point), else {s16 x, y, z, s16 matrix index} (GX_S16, 1.14 fixed point); GX ignores
             the frac argument for normals.
  colours    RGBA8 (GX_RGBA8, stride 4), GX_VA_CLR0; only present when flags bit31 is set (every
             model on the disc). trans_lit sets the lighting channel's material source to the
             register, not the vertex (flags bit30, never set on the disc), so the game ignores them.
  texcoords  {s16 s, t} with frac 8 (flags bit31; else u16 with frac 15), stride 4, GX_VA_TEX0.
  weights    weight_palette_num x Weight {u8 id[3], u8 num, u8 wht[4]} (percent); when
             weight_ext_num > 0xFF the table is weight_ext_num x WeightExt {u16 idx[3], u16 num,
             u8 weight[4]} (MakeWeightPaletteExt; two room models, r10c:27 = r22a:27 with 275
             entries, none in the em archives). MakeWeightPalette: palette[i] = sum over
             j < num of mtx[id[j]] * (wht[j] / 100), the last weight taking 1 - sum of the
             previous ones; mtx[k] = calcWeightMat: parts k's world matrix x its bind matrix
             (inverse of the rest-pose world translation, cModel::setPartsOffset), relative to
             parts 0 (the draw matrix is parts 0's). CalcSk1_x multiplies every vertex by
             palette[vertex matrix index]. So vertices are in model space at the rest pose,
             skinned by the parts of Weight entry [matrix index]: a glTF skin with inverse
             bind matrices from the rest pose.
  parts      displist_num x ModelPart (0x20 header: material bytes at 0x0B..0x17, u32 size at 0x18,
             u32 nPoly at 0x1C) followed by `size` bytes of GX display list, 32-byte aligned:
             opcode | vertex format (only format 0 on the disc), u16 vertex count, per vertex the
             u16 indices in GX attribute order: position, normal, colour, texcoord; 0x00 = GX_NOP
             pads the list. Opcodes on the disc: 0x80 quads, 0x90 triangles, 0x98 triangle strip.
             GXCallDisplayList(part + 0x20, size) after materialSetup binds texture texId
             (alphaSetup: alphaTex when flags bit2, alpha compare > alphaRef).
  blend      s32 count, count x {u16 dst, a, c, percent} (cModel::setJointInfo -> MotionWork::blendTbl);
             not padded: the flip table follows it directly
  flip       u32 count (= nParts), count x u16 parts remap (MotionWork::flip = flipTbl + 4), 0xCD padded
  shape      the morph targets of the head models (game/shape.cpp CalculateShape_new: tbl =
             shapeOfs + 4): u32 count, count x ShapeEntry {u32 ofs from tbl, s32 num}, then the
             delta lists back to back (ofs = 8 * count, 8 * count + 8 * num[0], ...): num x
             {s16 vertex index, s16 dx, dy, dz} in the vertex units (1 / (1 << shift) mm). Per
             frame the game copies vtxOrig (ResetShape) and adds weight x delta for each active
             shape channel (weight = Hermite key percent / 100), before the skinning; the normals
             are not touched. Zero padded to 32.
"""
import struct
from dataclasses import dataclass, field

ALIGN = 0x20
FILL = 0xCD
VERSION_NEW = 0x20030818
VERSION_OLD = 0x20010801
FLAG_TEX_S16_CLR = 0x80000000   # s16 texcoords frac 8 and a colour array (commonModelTrans `(s32) d->flags < 0`)
FLAG_NRM_S8 = 0x20000000

OP_QUADS = 0x80
OP_TRIANGLES = 0x90
OP_STRIP = 0x98
OPCODES = {OP_QUADS: 'quads', OP_TRIANGLES: 'triangles', OP_STRIP: 'strip'}
VERTEX_SIZE = 8   # four u16 indices


def align(n):
    return (n + ALIGN - 1) & ~(ALIGN - 1)


@dataclass
class Head:
    """ModelDataHead record: parts number, parent (0xFF = the model), two unknown bytes, position."""
    parts_no: int
    parent_no: int
    x2: int
    x3: int
    center: tuple


@dataclass
class Weight:
    ids: tuple      # u8 id[3] (parts indices)
    num: int
    wht: tuple      # u8 wht[4] percent

    def pairs(self):
        """[(parts, weight 0..1)] as MakeWeightPalette blends them (last takes the remainder)."""
        out = []
        total = 0.0
        for j in range(self.num):
            rate = self.wht[j] * 0.01
            if j == self.num - 1:
                rate = 1.0 - total
            total += rate
            out.append((self.ids[j], rate))
        return out


@dataclass
class Prim:
    op: int          # opcode with the vertex format bits (0x80 / 0x90 / 0x98)
    verts: list      # (pos, nrm, clr, tex) index tuples


@dataclass
class Part:
    flags: int       # ModelPart.flags (0x0B): bit0 bump, bit2 alpha texture, bit7 specularSetup2
    tex_id: int
    bump_tex: int
    alpha_tex: int
    spec_tex: int
    spec_rgb: tuple
    spec_type: int
    alpha_ref: int
    spec_pow: int
    pad_16: int
    spec_tex_org: int
    n_poly: int
    size: int        # display list byte length (stream + NOP padding)
    prims: list = field(default_factory=list)

    def stream_len(self):
        return sum(3 + VERTEX_SIZE * len(p.verts) for p in self.prims)

    def triangles(self):
        """(pos, nrm, clr, tex) index triples in GX winding (strips alternate, quads split 0-1-2 / 0-2-3)."""
        out = []
        for p in self.prims:
            v = p.verts
            if p.op == OP_TRIANGLES:
                out += [(v[i], v[i + 1], v[i + 2]) for i in range(0, len(v) - 2, 3)]
            elif p.op == OP_QUADS:
                for i in range(0, len(v) - 3, 4):
                    out += [(v[i], v[i + 1], v[i + 2]), (v[i], v[i + 2], v[i + 3])]
            elif p.op == OP_STRIP:
                for i in range(len(v) - 2):
                    out.append((v[i], v[i + 1], v[i + 2]) if i % 2 == 0 else (v[i + 1], v[i], v[i + 2]))
            else:
                raise ValueError(f'opcode {p.op:#x}')
        return out


@dataclass
class Mesh:
    version: int
    flags: int
    shift: int
    n_tex: int
    weight_palette_num: int
    weight_ext_num: int
    x8: int               # header word 0x08 (0x50 / 0)
    heads: list           # Head per parts
    vtx: list             # (x, y, z, matrix index) raw s16
    nrm: list             # (x, y, z, matrix index) raw s8 / s16
    clr: list             # u32 RGBA
    tex: list             # (s, t) raw s16
    weights: list         # Weight
    parts: list           # Part
    blend_table: list = None   # (dst, a, c, percent)
    flip_table: list = None    # u16 per parts
    shapes: list = None        # per shape key: [(vertex index, dx, dy, dz)] raw s16; None: no shape table
    fill: int = FILL           # the final padding byte after the flip table: 0xCD (archives), 0x00 (event bins)

    @property
    def n_parts(self):
        return len(self.heads)

    def shape_deltas(self, k):
        """{vertex index: (dx, dy, dz) mm} of shape key k at weight 1 (Hermite percent 100)."""
        s = 1.0 / (1 << self.shift)
        return {i: (dx * s, dy * s, dz * s) for i, dx, dy, dz in self.shapes[k]}

    @property
    def nrm_s8(self):
        return bool(self.flags & FLAG_NRM_S8)

    def position(self, i):
        """Vertex i in millimetres (GXSetVtxAttrFmt frac = shift)."""
        s = 1.0 / (1 << self.shift)
        x, y, z, _ = self.vtx[i]
        return (x * s, y * s, z * s)

    def normal(self, i):
        x, y, z, _ = self.nrm[i]
        s = 1.0 / 64 if self.nrm_s8 else 1.0 / 16384
        return (x * s, y * s, z * s)

    def texcoord(self, i):
        s, t = self.tex[i]
        return (s / 256.0, t / 256.0)

    def colour(self, i):
        c = self.clr[i]
        return ((c >> 24) & 0xFF, (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF)

    def skin(self, i):
        """[(parts, weight)] of vertex i: MakeWeightPalette entry [matrix index] (CalcSk1_x)."""
        return self.weights[self.vtx[i][3]].pairs()

    def n_triangles(self):
        return sum(len(p.triangles()) for p in self.parts)


def _hdr_size(version):
    if version == VERSION_NEW:
        return 0x48
    if version == VERSION_OLD:
        return 0x40
    raise ValueError(f'model version {version:#x}')


def _zero_pad(d, start, end, what):
    if end < start:
        raise ValueError(f'{what}: content runs {start - end} bytes past the next section')
    if end - start >= ALIGN or d[start:end] != b'\0' * (end - start):
        raise ValueError(f'{what}: bytes at {start:#x}..{end:#x} are not zero padding to 32')


def parse(d: bytes) -> Mesh:
    (p_head, x4, x8, p_clr, p_tex, p_weight, wpn, n_parts, n_dl, p_parts, flags, n_tex, shift, pad29, wext, shape_ofs,
     p_vtx, p_nrm, n_vtx, n_nrm, version) = struct.unpack('>IIIIIIBBHIIIBBHIIIHHI', d[:0x40])
    if p_clr & 0x80000000:
        raise ValueError('model header is relocated (memory image), expected file offsets')
    hs = _hdr_size(version)
    if x4 != 0 or pad29 != 0:
        raise ValueError('header padding not zero')
    if not (flags & FLAG_TEX_S16_CLR):
        raise ValueError(f'flags {flags:#x}: no colour array / u16 texcoords (not on the disc, vertex layout unknown)')
    blend_ofs = flip_ofs = 0
    if version == VERSION_NEW:
        blend_ofs, flip_ofs = struct.unpack('>II', d[0x40:0x48])
    secs = {'head': p_head, 'vtx': p_vtx, 'nrm': p_nrm, 'clr': p_clr, 'tex': p_tex, 'wgt': p_weight, 'parts': p_parts}
    if shape_ofs:
        secs['shape'] = shape_ofs
    if blend_ofs:
        secs['blend'] = blend_ofs
    if flip_ofs:
        secs['flip'] = flip_ofs
    order = sorted(secs, key=secs.get)
    expect = ['head', 'vtx', 'nrm'] + (['shape'] if shape_ofs else []) + ['clr', 'tex', 'wgt', 'parts'] + \
        (['blend'] if blend_ofs else []) + (['flip'] if flip_ofs else [])
    if order != expect:
        raise ValueError(f'section order {order}, expected {expect}')
    ends = {a: (secs[b] if b else len(d)) for a, b in zip(order, order[1:] + [None])}
    for name in order:
        # the flip table follows the blend table directly (4-aligned), the 0xCD padding comes after it
        if secs[name] & (ALIGN - 1) and not (name == 'flip' and blend_ofs):
            raise ValueError(f'{name} section at {secs[name]:#x} not 32-byte aligned')
    _zero_pad(d, hs, p_head, 'header tail')

    heads = []
    for i in range(n_parts):
        r = d[p_head + 16 * i:p_head + 16 * i + 16]
        heads.append(Head(r[0], r[1], r[2], r[3], struct.unpack('>3f', r[4:16])))
    _zero_pad(d, p_head + 16 * n_parts, ends['head'], 'parts records')

    vtx = [struct.unpack_from('>4h', d, p_vtx + 8 * i) for i in range(n_vtx)]
    _zero_pad(d, p_vtx + 8 * n_vtx, ends['vtx'], 'vertices')
    if flags & FLAG_NRM_S8:
        nrm = [struct.unpack_from('>3bB', d, p_nrm + 4 * i) for i in range(n_nrm)]
        _zero_pad(d, p_nrm + 4 * n_nrm, ends['nrm'], 'normals')
    else:
        nrm = [struct.unpack_from('>4h', d, p_nrm + 8 * i) for i in range(n_nrm)]
        _zero_pad(d, p_nrm + 8 * n_nrm, ends['nrm'], 'normals')
    shapes = None
    if shape_ofs:
        cnt, = struct.unpack_from('>I', d, shape_ofs)
        tbl = shape_ofs + 4
        shapes = []
        p = tbl + 8 * cnt
        for k in range(cnt):
            ofs, num = struct.unpack_from('>Ii', d, tbl + 8 * k)
            if tbl + ofs != p or num < 0:
                raise ValueError(f'shape {k}: delta list at {ofs:#x} ({num} entries), expected {p - tbl:#x}')
            deltas = [struct.unpack_from('>4h', d, p + 8 * i) for i in range(num)]
            if any(e[0] >= n_vtx for e in deltas):
                raise ValueError(f'shape {k}: vertex index out of range')
            shapes.append(deltas)
            p += 8 * num
        _zero_pad(d, p, ends['shape'], 'shape table')

    weights = []
    if wext > 0xFF:     # commonScreenMatSub: MakeWeightPaletteExt((WeightExt*) pWeight, weight_ext_num)
        for i in range(wext):
            w = struct.unpack_from('>3HH4B', d, p_weight + 12 * i)
            weights.append(Weight(tuple(w[:3]), w[3], tuple(w[4:8])))
        _zero_pad(d, p_weight + 12 * wext, ends['wgt'], 'weights')
    else:
        for i in range(wpn):
            w = d[p_weight + 8 * i:p_weight + 8 * i + 8]
            weights.append(Weight(tuple(w[:3]), w[3], tuple(w[4:8])))
        _zero_pad(d, p_weight + 8 * wpn, ends['wgt'], 'weights')

    parts = []
    o = p_parts
    max_clr = max_tex = -1
    for k in range(n_dl):
        h = d[o:o + 0x20]
        if h[:0xB] != b'\0' * 0xB:
            raise ValueError(f'part {k}: header bytes 0..0xA not zero')
        size, n_poly = struct.unpack('>II', h[0x18:0x20])
        part = Part(h[0xB], h[0xC], h[0xD], h[0xE], h[0xF], tuple(h[0x10:0x13]), h[0x13], h[0x14], h[0x15], h[0x16], h[0x17],
                    n_poly, size)
        p = o + 0x20
        end = p + size
        if size & (ALIGN - 1) or end > ends['parts']:
            raise ValueError(f'part {k}: display list size {size:#x}')
        while p < end:
            op = d[p]
            if op == 0:
                break
            if op & 0xF8 not in OPCODES or op & 7:
                raise ValueError(f'part {k}: opcode {op:#x} at {p:#x}')
            n, = struct.unpack_from('>H', d, p + 1)
            p += 3
            if p + VERTEX_SIZE * n > end:
                raise ValueError(f'part {k}: {n} vertices at {p:#x} run past the display list')
            verts = [struct.unpack_from('>4H', d, p + VERTEX_SIZE * i) for i in range(n)]
            p += VERTEX_SIZE * n
            for v in verts:
                if v[0] >= n_vtx or v[1] >= n_nrm:
                    raise ValueError(f'part {k}: vertex index {v} out of range')
                max_clr = max(max_clr, v[2])
                max_tex = max(max_tex, v[3])
            part.prims.append(Prim(op, verts))
        if d[p:end] != b'\0' * (end - p):
            raise ValueError(f'part {k}: display list tail at {p:#x} is not NOP padding')
        parts.append(part)
        o = end
    _zero_pad(d, o, ends['parts'], 'display lists')

    clr = list(struct.unpack_from(f'>{max_clr + 1}I', d, p_clr))
    _zero_pad(d, p_clr + 4 * len(clr), ends['clr'], 'colours')
    tex = [struct.unpack_from('>2h', d, p_tex + 4 * i) for i in range(max_tex + 1)]
    _zero_pad(d, p_tex + 4 * len(tex), ends['tex'], 'texcoords')

    blend = flip = None
    if blend_ofs:
        cnt, = struct.unpack_from('>i', d, blend_ofs)
        blend = [struct.unpack_from('>4H', d, blend_ofs + 4 + 8 * i) for i in range(cnt)]
        if blend_ofs + 4 + 8 * cnt != ends['blend']:
            raise ValueError(f'blend table: {ends["blend"] - blend_ofs - 4 - 8 * cnt} bytes between the table and the flip table')
    if flip_ofs:
        cnt, = struct.unpack_from('>I', d, flip_ofs)
        if cnt != n_parts:
            raise ValueError(f'flip table count {cnt} != nParts {n_parts}')
        flip = list(struct.unpack_from(f'>{cnt}H', d, flip_ofs + 4))
        p = flip_ofs + 4 + 2 * cnt
        tail = d[p:]
        if len(tail) >= ALIGN or (tail and tail not in (bytes([FILL]) * len(tail), b'\0' * len(tail))):
            raise ValueError(f'flip table tail at {p:#x} is not 0xCD / 0x00 padding to 32')
        fill = tail[0] if tail else FILL
    else:
        fill = FILL
    return Mesh(version, flags, shift, n_tex, wpn, wext, x8, heads, vtx, nrm, clr, tex, weights, parts, blend, flip, shapes, fill)


def serialise(m: Mesh) -> bytes:
    hs = _hdr_size(m.version)
    sections = []   # (name, bytes, pad byte or None: no padding)

    def add(name, b, fill=0):
        sections.append((name, bytes(b), fill))

    add('head', b''.join(struct.pack('>4B3f', h.parts_no, h.parent_no, h.x2, h.x3, *h.center) for h in m.heads))
    add('vtx', b''.join(struct.pack('>4h', *v) for v in m.vtx))
    add('nrm', b''.join(struct.pack('>3bB' if m.nrm_s8 else '>4h', *v) for v in m.nrm))
    if m.shapes is not None:
        sb = struct.pack('>I', len(m.shapes))
        ofs = 8 * len(m.shapes)
        for deltas in m.shapes:
            sb += struct.pack('>Ii', ofs, len(deltas))
            ofs += 8 * len(deltas)
        add('shape', sb + b''.join(struct.pack('>4h', *e) for deltas in m.shapes for e in deltas))
    add('clr', struct.pack(f'>{len(m.clr)}I', *m.clr))
    add('tex', b''.join(struct.pack('>2h', *t) for t in m.tex))
    if m.weight_ext_num > 0xFF:
        add('wgt', b''.join(struct.pack('>3HH4B', *w.ids, w.num, *w.wht) for w in m.weights))
    else:
        add('wgt', b''.join(struct.pack('>3BB4B', *w.ids, w.num, *w.wht) for w in m.weights))
    pb = bytearray()
    for p in m.parts:
        stream = bytearray()
        for pr in p.prims:
            stream += struct.pack('>BH', pr.op, len(pr.verts))
            for v in pr.verts:
                stream += struct.pack('>4H', *v)
        if len(stream) > p.size:
            raise ValueError('display list longer than the part size')
        stream += b'\0' * (p.size - len(stream))
        pb += b'\0' * 0xB + struct.pack('>5B3B5BII', p.flags, p.tex_id, p.bump_tex, p.alpha_tex, p.spec_tex, *p.spec_rgb,
                                          p.spec_type, p.alpha_ref, p.spec_pow, p.pad_16, p.spec_tex_org, p.size, p.n_poly)
        pb += stream
    add('parts', pb)
    if m.blend_table is not None:
        add('blend', struct.pack('>i', len(m.blend_table)) + b''.join(struct.pack('>4H', *e) for e in m.blend_table), None)
    if m.flip_table is not None:
        add('flip', struct.pack(f'>I{len(m.flip_table)}H', len(m.flip_table), *m.flip_table), m.fill)

    ofs = {}
    out = bytearray(b'\0' * align(hs))
    for name, b, fill in sections:
        ofs[name] = len(out)
        out += b
        if fill is not None:
            out += bytes([fill]) * (align(len(out)) - len(out))
    struct.pack_into('>IIIIIIBBHIIIBBHIIIHHI', out, 0, ofs['head'], 0, m.x8, ofs['clr'], ofs['tex'], ofs['wgt'], m.weight_palette_num,
                     m.n_parts, len(m.parts), ofs['parts'], m.flags, m.n_tex, m.shift, 0, m.weight_ext_num, ofs.get('shape', 0),
                     ofs['vtx'], ofs['nrm'], len(m.vtx), len(m.nrm), m.version)
    if m.version == VERSION_NEW:
        struct.pack_into('>II', out, 0x40, ofs.get('blend', 0), ofs.get('flip', 0))
    return bytes(out)


def describe(m: Mesh):
    ops = {}
    for p in m.parts:
        for pr in p.prims:
            ops[OPCODES[pr.op & 0xF8]] = ops.get(OPCODES[pr.op & 0xF8], 0) + 1
    return (f'{len(m.vtx)} vertices, {len(m.nrm)} normals ({"s8" if m.nrm_s8 else "s16"}), {len(m.clr)} colours, '
            f'{len(m.tex)} texcoords, {len(m.weights)} weight entries, {len(m.parts)} parts, {m.n_triangles()} triangles '
            f'({", ".join(f"{v} {k}" for k, v in sorted(ops.items()))}), {m.n_tex} textures, shift {m.shift}'
            + (f', {len(m.shapes)} shape keys ({", ".join(str(len(s)) for s in m.shapes)} vertex deltas)' if m.shapes else ''))
