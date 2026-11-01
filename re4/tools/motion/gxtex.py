"""GameCube TPL texture palettes ("TPL" archive entries) and GX texture decoding to RGBA8 / PNG.

TPL (include/tpl.h, game/model.cpp calcTplAddr relocates the offsets): u32 version 0x0020AF30,
u32 numDescriptors, u32 descriptor array offset; descriptors {u32 TEXHeader offset, u32 CLUT offset};
TEXHeader {u16 height, u16 width, u32 format, u32 data offset, u32 wrapS, u32 wrapT, u32 minFilter,
u32 magFilter, f32 LODBias, u8 edgeLODEnable, u8 minLOD, u8 maxLOD, u8 unpacked}. commonModelTrans
(game/trans.cpp) builds one GXTexObj per descriptor with these fields; mipmaps (maxLOD > 0) follow
the base level in `data`, only the base level is decoded here.

Texture formats on the disc's character archives: GX_TF_CMPR (14), GX_TF_IA8 (3), GX_TF_I4 (0); no
CLUTs. Layouts (Dolphin's TextureDecoder is the reference):
  I4    8x8 texel tiles, 4 bits per texel, the high nibble is the left texel; I = n * 0x11, A = I
  IA8   4x4 tiles, u16 per texel: high byte alpha, low byte intensity
  CMPR  8x8 tiles of four DXT1-style 4x4 blocks (top-left, top-right, bottom-left, bottom-right),
        block = u16 BE colour0, u16 BE colour1 (RGB565), 4 index bytes with the LEFT texel in the
        HIGH two bits; colour0 > colour1: 4 colours with the hardware's 5/8-3/8 blend
        (Dolphin DXTBlend), else colour2 = average, colour3 = transparent average
I4 and IA8 are lossless: `encode` inverts `decode` byte for byte (the round-trip check).
"""
import struct
import zlib

import numpy as np

TPL_VERSION = 0x0020AF30
FMT_I4 = 0
FMT_IA8 = 3
FMT_CMPR = 14
FMT_NAMES = {FMT_I4: 'I4', FMT_IA8: 'IA8', FMT_CMPR: 'CMPR'}


class Texture:
    def __init__(self, index, width, height, fmt, data, wrap_s, wrap_t, min_lod, max_lod):
        self.index = index
        self.width = width
        self.height = height
        self.fmt = fmt
        self.data = data        # base level bytes
        self.wrap_s = wrap_s
        self.wrap_t = wrap_t
        self.min_lod = min_lod
        self.max_lod = max_lod

    @property
    def fmt_name(self):
        return FMT_NAMES[self.fmt]

    def decode(self):
        return decode(self.fmt, self.width, self.height, self.data)


def base_size(fmt, w, h):
    if fmt == FMT_I4:
        return ((w + 7) // 8) * ((h + 7) // 8) * 32
    if fmt == FMT_IA8:
        return ((w + 3) // 4) * ((h + 3) // 4) * 32
    if fmt == FMT_CMPR:
        return ((w + 7) // 8) * ((h + 7) // 8) * 32
    raise ValueError(f'texture format {fmt} (not on the disc)')


def parse_tpl(d: bytes):
    version, n, ofs = struct.unpack('>III', d[:12])
    if version != TPL_VERSION:
        raise ValueError(f'TPL version {version:#x}')
    out = []
    for i in range(n):
        th, clut = struct.unpack_from('>II', d, ofs + 8 * i)
        if clut:
            raise ValueError(f'texture {i}: CLUT textures not supported')
        h, w, fmt, data, ws, wt, minf, magf, lod, edge, minl, maxl, unpacked = struct.unpack_from('>HHIIIIIIfBBBB', d, th)
        if unpacked:
            raise ValueError(f'texture {i}: header is relocated (memory image)')
        size = base_size(fmt, w, h)
        if data + size > len(d):
            raise ValueError(f'texture {i}: data runs past the palette')
        out.append(Texture(i, w, h, fmt, d[data:data + size], ws, wt, minl, maxl))
    return out


def _tiles(a, w, h, tw, th, crop=True):
    """Texels (n, c) in tile order (row-major tiles, row-major within a tile) -> (h, w, c) image;
    crop=False keeps the whole tile-rounded image (the padding texels of a texture smaller than a tile)."""
    rows, cols = (h + th - 1) // th, (w + tw - 1) // tw
    a = a.reshape(rows, cols, th, tw, -1).transpose(0, 2, 1, 3, 4)
    a = a.reshape(rows * th, cols * tw, -1)
    return a[:h, :w] if crop else a


def _untile(img, tw, th):
    """(h, w, ...) image (dimensions multiples of the tile) -> tile-ordered (n, th, tw, ...)."""
    h, w = img.shape[:2]
    a = img.reshape(h // th, th, w // tw, tw, *img.shape[2:])
    a = a.transpose(0, 2, 1, 3, *range(4, a.ndim))
    return a.reshape(-1, th, tw, *img.shape[2:])


def _c5(v):
    return (v << 3) | (v >> 2)


def _c6(v):
    return (v << 2) | (v >> 4)


def _rgb565(c):
    c = c.astype(np.uint32)
    return np.stack([_c5(c >> 11), _c6((c >> 5) & 0x3F), _c5(c & 0x1F)], axis=-1).astype(np.uint8)


def decode(fmt, w, h, data: bytes, crop=True):
    """RGBA8 (h, w, 4) uint8 of the base level (crop=False: tile-rounded, see _tiles)."""
    if fmt == FMT_I4:
        b = np.frombuffer(data, np.uint8)
        px = np.stack([b >> 4, b & 0xF], axis=-1).reshape(-1) * np.uint8(0x11)
        return _tiles(np.repeat(px[:, None], 4, axis=1), w, h, 8, 8, crop)
    if fmt == FMT_IA8:
        b = np.frombuffer(data, np.uint8).reshape(-1, 2)   # alpha, intensity
        px = np.stack([b[:, 1], b[:, 1], b[:, 1], b[:, 0]], axis=-1)
        return _tiles(px, w, h, 4, 4, crop)
    if fmt == FMT_CMPR:
        blocks = np.frombuffer(data, np.uint8).reshape(-1, 8)
        n = len(blocks)
        c0 = (blocks[:, 0].astype(np.uint32) << 8) | blocks[:, 1]
        c1 = (blocks[:, 2].astype(np.uint32) << 8) | blocks[:, 3]
        r0, r1 = _rgb565(c0).astype(np.uint32), _rgb565(c1).astype(np.uint32)
        four = (c0 > c1)[:, None]
        pal = np.zeros((n, 4, 4), np.uint8)
        pal[:, 0, :3] = r0
        pal[:, 1, :3] = r1
        pal[:, 0, 3] = pal[:, 1, 3] = 255
        avg = (r0 + r1) // 2
        pal[:, 2, :3] = np.where(four, (r1 * 3 + r0 * 5) >> 3, avg)
        pal[:, 3, :3] = np.where(four, (r0 * 3 + r1 * 5) >> 3, avg)
        pal[:, 2, 3] = 255
        pal[:, 3, 3] = np.where(four[:, 0], 255, 0)
        idx = blocks[:, 4:8, None] >> np.array([6, 4, 2, 0], np.uint8)[None, None, :] & 3   # (n, 4 rows, 4 cols)
        px = pal[np.arange(n)[:, None, None], idx]                                            # (n, 4, 4, 4)
        # blocks -> 8x8 tiles: block order TL, TR, BL, BR
        tiles = px.reshape(-1, 2, 2, 4, 4, 4).transpose(0, 1, 3, 2, 4, 5)
        return _tiles(tiles.reshape(-1, 4), w, h, 8, 8, crop)
    raise ValueError(f'texture format {fmt}')


def encode(fmt, img):
    """RGBA8 (h, w, 4) -> texture bytes (I4 / IA8, the lossless formats). Dimensions must be tile multiples."""
    h, w = img.shape[:2]
    if fmt == FMT_I4:
        n = (img[..., 0] >> 4).astype(np.uint8)
        t = _untile(n, 8, 8).reshape(-1, 2)
        return ((t[:, 0] << 4) | t[:, 1]).astype(np.uint8).tobytes()
    if fmt == FMT_IA8:
        t = _untile(img, 4, 4).reshape(-1, 4)
        return np.stack([t[:, 3], t[:, 0]], axis=-1).astype(np.uint8).tobytes()
    raise ValueError(f'encode: format {fmt} is lossy or unsupported')


def png(img) -> bytes:
    """RGBA8 (h, w, 4) -> PNG file bytes."""
    img = np.ascontiguousarray(img, dtype=np.uint8)
    h, w = img.shape[:2]
    raw = b''.join(b'\0' + img[y].tobytes() for y in range(h))

    def chunk(tag, body):
        c = tag + body
        return struct.pack('>I', len(body)) + c + struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def verify(textures):
    """Round-trips the lossless textures; decodes the rest. Returns (n_lossless, n_ok, [failure names])."""
    n = ok = 0
    fails = []
    for t in textures:
        img = t.decode()
        if t.fmt in (FMT_I4, FMT_IA8):
            n += 1
            tw = 8 if t.fmt == FMT_I4 else 4
            if t.width % tw or t.height % tw:
                # smaller than a tile (the 2x2 textures of the room ETM models): the file holds the
                # whole tile, so the round trip runs on the uncropped image
                img = decode(t.fmt, t.width, t.height, t.data, crop=False)
            if encode(t.fmt, img) == t.data:
                ok += 1
            else:
                fails.append(f'texture {t.index} ({t.fmt_name} {t.width}x{t.height}): re-encoding differs')
    return n, ok, fails
