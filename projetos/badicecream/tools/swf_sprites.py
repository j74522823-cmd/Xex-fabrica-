"""Resolve símbolo (classe) -> sprite -> frames -> bitmaps (id do PNG + matriz). Uso: swf_sprites.py jogo.swf saida.json"""
import sys, zlib, struct, json

class BR:
    def __init__(s, b, p=0): s.b = b; s.p = p; s.bit = 0
    def ub(s, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | ((s.b[s.p] >> (7 - s.bit)) & 1); s.bit += 1
            if s.bit == 8: s.bit = 0; s.p += 1
        return v
    def sb(s, n):
        v = s.ub(n)
        return v - (1 << n) if n and v >> (n-1) else v
    def align(s):
        if s.bit: s.bit = 0; s.p += 1

def matrix(r):
    sx, sy, k0, k1 = 1.0, 1.0, 0.0, 0.0
    if r.ub(1): n = r.ub(5); sx = r.sb(n)/65536; sy = r.sb(n)/65536
    if r.ub(1): n = r.ub(5); k0 = r.sb(n)/65536; k1 = r.sb(n)/65536
    n = r.ub(5); tx = r.sb(n)/20; ty = r.sb(n)/20
    r.align(); return [sx, k0, k1, sy, tx, ty]

def rect(r):
    n = r.ub(5); [r.sb(n) for _ in range(4)]; r.align()

def tags(buf, off, end):
    while off < end:
        h = struct.unpack('<H', buf[off:off+2])[0]; t = h >> 6; l = h & 63; off += 2
        if l == 63: l = struct.unpack('<I', buf[off:off+4])[0]; off += 4
        yield t, buf[off:off+l]; off += l

d = open(sys.argv[1], 'rb').read()
body = zlib.decompress(d[8:]) if d[:3] == b'CWS' else d[8:]
n = body[0] >> 3; off = (5 + 4*n + 7)//8 + 4

bitmaps = set(); shapes = {}; sprites = {}; symbols = {}

def parse_shape(t, p):
    """Procura fills de bitmap (tipo 0x40..0x43) em DefineShape/2/3: devolve (bitmap id, matriz)."""
    cid = struct.unpack('<H', p[:2])[0]; r = BR(p, 2); rect(r)
    if t == 83: rect(r); r.ub(8)  # DefineShape4: edge bounds + flags
    r.align()
    nf = p[r.p]; r.p += 1
    if nf == 255: nf = struct.unpack('<H', p[r.p:r.p+2])[0]; r.p += 2
    out = []
    for _ in range(nf):
        ft = p[r.p]; r.p += 1
        if ft == 0: r.p += 3 if t in (2, 22) else 4
        elif ft in (0x10, 0x12, 0x13):
            rr = BR(p, r.p); matrix(rr); rr.align()
            ng = rr.ub(8) & 0xf; rr.p += 0  # approximate
            return None  # gradientes não usados
        elif ft in (0x40, 0x41, 0x42, 0x43):
            bid = struct.unpack('<H', p[r.p:r.p+2])[0]; r.p += 2
            rr = BR(p, r.p); m = matrix(rr); r.p = rr.p
            out.append((bid, m))
        else: return None
    return cid, out

place_cache = {}
def parse_place(p):
    f = p[0]; depth = struct.unpack('<H', p[1:3])[0]; q = 3
    cid = None; m = None
    if f & 2: cid = struct.unpack('<H', p[q:q+2])[0]; q += 2
    if f & 4: r = BR(p, q); m = matrix(r); q = r.p
    return f, depth, cid, m

def parse_sprite(p):
    cid, nframes = struct.unpack('<HH', p[:4])
    frames = []; disp = {}; label = None; labels = {}
    for t, q in tags(p, 4, len(p)):
        if t == 26:
            f, depth, c, m = parse_place(q)
            if f & 1 and not (f & 2): pass
            cur = disp.get(depth)
            if (f & 2) and not (f & 1 and False): disp[depth] = {'id': c, 'm': m or [1,0,0,1,0,0]}
            elif cur and m: cur['m'] = m
        elif t == 28:
            disp.pop(struct.unpack('<H', q[:2])[0], None)
        elif t == 43:
            labels[q[:q.index(b'\0')].decode()] = len(frames)
        elif t == 1:
            frames.append([dict(v, depth=k) for k, v in sorted(disp.items())])
    return cid, {'frames': frames, 'labels': labels}

for t, p in tags(body, off, len(body)):
    if t in (20, 36): bitmaps.add(struct.unpack('<H', p[:2])[0])
    elif t in (2, 22, 32, 83):
        r = parse_shape(t, p)
        if r: shapes[r[0]] = r[1]
    elif t == 39:
        cid, s = parse_sprite(p); sprites[cid] = s
    elif t == 76:
        cnt = struct.unpack('<H', p[:2])[0]; q = 2
        for _ in range(cnt):
            cid = struct.unpack('<H', p[q:q+2])[0]; q += 2
            e = p.index(b'\0', q); symbols[cid] = p[q:e].decode(); q = e+1

json.dump(dict(bitmaps=sorted(bitmaps), shapes={k: v for k, v in shapes.items() if v}, sprites=sprites, symbols=symbols), open(sys.argv[2], 'w'))
print(len(bitmaps), 'bitmaps', len(shapes), 'shapes', len(sprites), 'sprites', len(symbols), 'símbolos')
