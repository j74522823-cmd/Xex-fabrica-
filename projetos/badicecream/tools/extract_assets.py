"""Extrai bitmaps (PNG), sons (MP3/WAV) e o mapa SymbolClass de um SWF.
Uso: python3 -I extract_assets.py jogo.swf pasta_saida"""
import sys, zlib, struct, os, json
from PIL import Image

swf, out = sys.argv[1], sys.argv[2]
d = open(swf, 'rb').read()
body = zlib.decompress(d[8:]) if d[:3] == b'CWS' else d[8:]
n = body[0] >> 3
off = (5 + 4*n + 7)//8 + 4
os.makedirs(out+'/img', exist_ok=True); os.makedirs(out+'/snd', exist_ok=True)
symbols = {}; sprites = {}; stats = dict(img=0, snd=0)
rate = [5512, 11025, 22050, 44100]

def tags(buf, off, end):
    while off < end:
        h = struct.unpack('<H', buf[off:off+2])[0]; t = h >> 6; l = h & 63; off += 2
        if l == 63: l = struct.unpack('<I', buf[off:off+4])[0]; off += 4
        yield t, buf[off:off+l]; off += l

for t, p in tags(body, off, len(body)):
    if t in (20, 36):  # DefineBitsLossless / 2
        cid, fmt, w, h = struct.unpack('<HBHH', p[:7])
        pos = 7
        if fmt == 3: cs = p[pos] + 1; pos += 1
        raw = zlib.decompress(p[pos:])
        alpha = (t == 36)
        if fmt == 5:
            a = bytearray(raw)
            im = Image.new('RGBA', (w, h))
            px = bytearray(w*h*4)
            for i in range(w*h):
                A, R, G, B = a[i*4:i*4+4]
                if alpha and A:  # des-premultiplica
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
                    c = pal[raw[base + y*stride + x]] if raw[base + y*stride + x] < cs else b'\0\0\0\0'
                    px += bytes((c[0], c[1], c[2], c[3])) if alpha else bytes((c[0], c[1], c[2], 255))
            im = Image.frombytes('RGBA', (w, h), bytes(px))
        else:
            continue
        im.save(f'{out}/img/{cid}.png'); stats['img'] += 1
    elif t == 14:  # DefineSound
        cid = struct.unpack('<H', p[:2])[0]
        flags = p[2]; fmt = flags >> 4
        if fmt == 2:   # MP3: pula 2 bytes de seek
            open(f'{out}/snd/{cid}.mp3', 'wb').write(p[9:] if False else p[7+2:]); stats['snd'] += 1
        elif fmt in (0, 3):  # PCM -> WAV
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
