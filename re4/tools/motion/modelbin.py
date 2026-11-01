"""Model .bin ("BIN" archive entries, game/model.cpp ModelData): the parts hierarchy and rest pose.

ModelData header (include/model.h): u32 pHead @0x00 (offset until calcModelAddr relocates it),
u8 nParts @0x19, u32 version @0x3C, u32 blendTbl @0x40 / flipTbl @0x44 (version 0x20030818;
cModel::setJointInfo). blendTbl: s32 count, then count x {u16 dst, a, c, percent}: MotionMove sets
parts dst's rotation to slerp(c, a, percent / 100) after the IK (double joints: elbows, knees).
pHead points at nParts ModelDataHead records of 16 bytes: u8 partsNo, u8 parentNo (0xFF = the
model), u8 x2, u8 x3, Vec center = the parts' rest position relative to its parent
(cModel::setPartsOffset copies it into cParts::pos; rotation zero, scale one).
"""
import struct
from dataclasses import dataclass


@dataclass
class Part:
    no: int
    parent: int        # -1 = the model
    x2: int
    x3: int
    pos: tuple         # rest translation relative to the parent (mm)
    attach: int        # ModelDataHead.partsNo: for attachment models (heads, hands) the parent model's parts


@dataclass
class Model:
    version: int
    parts: list
    blend_table: list = None   # (dst, a, c, percent) quaternion blends (MotionWork::blendTbl), version 0x20030818

    @property
    def n_parts(self):
        return len(self.parts)

    def children(self, i):
        return [p.no for p in self.parts if p.parent == i]

    def roots(self):
        return [p.no for p in self.parts if p.parent < 0]

    def check_tree(self):
        """Parents must precede their children (partsWorldCalc walks the list in order once)."""
        for p in self.parts:
            if p.parent >= p.no:
                raise ValueError(f'parts {p.no}: parent {p.parent} not earlier in the list')


def parse(d: bytes) -> Model:
    p_head, = struct.unpack('>I', d[:4])
    if p_head & 0x80000000:
        raise ValueError('model header is relocated (memory image), expected file offsets')
    n = d[0x19]
    version, = struct.unpack('>I', d[0x3C:0x40])
    parts = []
    for i in range(n):
        r = d[p_head + 16 * i:p_head + 16 * i + 16]
        pn, par, x2, x3 = r[:4]
        pos = struct.unpack('>3f', r[4:16])
        parts.append(Part(i, -1 if par > 0xFE else par, x2, x3, pos, pn))
    blend = None
    if version == 0x20030818:
        bt, = struct.unpack('>I', d[0x40:0x44])
        if bt:
            cnt, = struct.unpack('>i', d[bt:bt + 4])
            blend = [struct.unpack('>4H', d[bt + 4 + 8 * i:bt + 12 + 8 * i]) for i in range(cnt)]
    return Model(version, parts, blend)
