"""Extrai bitmaps (PNG), sons (MP3/WAV) e o mapa SymbolClass de um SWF.
Uso: python3 -I extract_assets.py jogo.swf pasta_saida

Suporta bitmaps lossless (DefineBitsLossless/2), JPEG2 e JPEG3 com alpha.
"""
import sys, zlib, struct, os, json, io
from PIL import Image

swf, out = sys.argv[1], sys.argv[2]
d = open(swf, 'rb').read()
if len(d) < 8 or d[:3] not in (b'CWS', b'FWS'):
    raise SystemExit("SWF inválido ou compressão não suportada (esperado CWS/FWS)")
body = zlib.decompress(d[8:]) if d[:3] == b'CWS' else d[8:]
n = body[0] >> 3
off = (5 + 4*n + 7)//8 + 4
os.makedirs(out+'/img', exist_ok=True); os.makedirs(out+'/snd', exist_ok=True)
symbols = {}; stats = dict(lossless=0, jpeg=0, jpeg_alpha=0, snd=0, skipped_bitmap=0)
rate = [5512, 11025, 22050, 44100]

def tags(buf, off, end):
    while off < end:
        if off + 2 > end: raise ValueError("cabeçalho de tag truncado")
        h = struct.unpack('<H', buf[off:off+2])[0]; t = h >> 6; l = h & 63; off += 2
        if l == 63:
            if off + 4 > end: raise ValueError("tamanho de tag truncado")
            l = struct.unpack('<I', buf[off:off+4])[0]; off += 4
        if off + l > end: raise ValueError("tag excede o tamanho do SWF")
        yield t, buf[off:off+l]; off += l

def save_lossless(tag, p):
    cid, fmt, w, h = struct.unpack('<HBHH', p[:7])
    pos = 7
    if fmt == 3: cs = p[pos] + 1; pos += 1
    raw = zlib.decompress(p[pos:])
    alpha = (tag == 36)
    if fmt == 5:
        if len(raw) < w*h*4: raise ValueError("bitmap RGBA lossless truncado")
        px = bytearray(w*h*4)
        for i in range(w*h):
            A, R, G, B = raw[i*4:i*4+4]
            if alpha and A:
                R = min(255, R*255//A); G = min(255, G*255//A); B = min(255, B*255//A)
            px[i*4:i*4+4] = bytes((R, G, B, A if alpha else 255))
        im = Image.frombytes('RGBA', (w, h), bytes(px))
    elif fmt == 3:
        esz = 4 if alpha else 3
        pal = [raw[i*esz:(i+1)*esz] for i in range(cs)]
        stride = (w + 3) & ~3; base = cs*esz
        px = bytearray()
        for y in range(h):
            for x in range(w):
                idx = raw[base + y*stride + x]
                c = pal[idx] if idx < cs else b'\0'*esz
                px += bytes((c[0], c[1], c[2], c[3])) if alpha else bytes((c[0], c[1], c[2], 255))
        im = Image.frombytes('RGBA', (w, h), bytes(px))
    else:
        return None
    return cid, im

def save_jpeg(tag, p):
    cid = struct.unpack('<H', p[:2])[0]
    if tag == 21:  # DefineBitsJPEG2
        jpeg, alpha_data = p[2:], None
    else:          # DefineBitsJPEG3: offset + JPEG + zlib alpha plane
        if len(p) < 6: raise ValueError("DefineBitsJPEG3 truncado")
        alpha_offset = struct.unpack('<I', p[2:6])[0]
        if alpha_offset > len(p)-6: raise ValueError("offset JPEG3 inválido")
        jpeg = p[6:6+alpha_offset]
        alpha_data = zlib.decompress(p[6+alpha_offset:])
    im = Image.open(io.BytesIO(jpeg)).convert('RGB')
    if alpha_data is not None:
        w, h = im.size
        if len(alpha_data) != w*h:
            raise ValueError(f"alpha JPEG3 tem {len(alpha_data)} bytes; esperado {w*h}")
        rgba = im.convert('RGBA')
        rgba.putalpha(Image.frombytes('L', (w, h), alpha_data))
        im = rgba
    else:
        im = im.convert('RGBA')
    return cid, im, alpha_data is not None

for t, p in tags(body, off, len(body)):
    if t in (20, 36):
        result = save_lossless(t, p)
        if result:
            cid, im = result; im.save(f'{out}/img/{cid}.png'); stats['lossless'] += 1
        else: stats['skipped_bitmap'] += 1
    elif t in (21, 35):
        try:
            cid, im, has_alpha = save_jpeg(t, p)
            im.save(f'{out}/img/{cid}.png')
            stats['jpeg_alpha' if has_alpha else 'jpeg'] += 1
        except Exception as e:
            stats['skipped_bitmap'] += 1
            print(f"aviso: bitmap JPEG (tag {t}) não extraído: {e}", file=sys.stderr)
    elif t == 14:  # DefineSound
        cid = struct.unpack('<H', p[:2])[0]
        flags = p[2]; fmt = flags >> 4
        if fmt == 2:
            open(f'{out}/snd/{cid}.mp3', 'wb').write(p[9:]); stats['snd'] += 1
        elif fmt in (0, 3):
            r = rate[(flags >> 2) & 3]; bits = 16 if flags & 2 else 8; ch = 2 if flags & 1 else 1
            data = p[7:]
            wav = b'RIFF' + struct.pack('<I', 36+len(data)) + b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 1, ch, r, r*ch*bits//8, ch*bits//8, bits) + b'data' + struct.pack('<I', len(data)) + data
            open(f'{out}/snd/{cid}.wav', 'wb').write(wav); stats['snd'] += 1
    elif t == 76:  # SymbolClass: id -> nome da classe
        cnt = struct.unpack('<H', p[:2])[0]; q = 2
        for _ in range(cnt):
            cid = struct.unpack('<H', p[q:q+2])[0]; q += 2
            e = p.index(b'\0', q); symbols[cid] = p[q:e].decode(); q = e+1
json.dump(symbols, open(out+'/symbols.json', 'w'), indent=1)
print(stats, len(symbols), 'símbolos')
