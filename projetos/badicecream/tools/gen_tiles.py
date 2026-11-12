"""Gera src/tile_table.hpp (andável + pegada em células por tile) e testa a alcançabilidade das 40 fases.
Uso: python3 -I tools/gen_tiles.py <raiz do projeto>"""
import json, math, re, sys, glob, collections
root = sys.argv[1]
atlas = json.load(open(root + '/assets/atlas/atlas.json'))
names = re.findall(r'"(\w+)"', re.search(r'kTileNames\[\] = \{(.*?)\};', open(root + '/src/game_ids.hpp').read(), re.S).group(1))
FREE = {'LandTile', 'LargeGroundHole', 'LargeSnowMound', 'MedGroundHole', 'SmallGroundHole', 'SmallSnowMound', 'SnowSprig',
        'SideSnowLeft', 'SideSnowRight', 'SnowySideLeft', 'SnowySideRight', 'Stones1', 'Stones2', 'Stones3'} | {'MeltedSnow%d' % i for i in range(1, 13)}
foot = []
for n in names:
    if '_' not in atlas[n]:
        foot.append((False, 1, 1)); continue
    fr = atlas[n]['_'][0]
    fw = max(1, math.ceil(fr['w'] / 36 - 0.01))
    fh = max(1, math.ceil((fr['h'] - fr['oy']) / 36 - 0.01))
    foot.append((n in FREE, fw, fh))
out = ['// GERADO por tools/gen_tiles.py -- não editar.', '#pragma once', 'namespace bic {',
       'struct TileInfo { bool free; int fw, fh; };  // pegada em células (a partir do canto sup. esq.)',
       'inline const TileInfo kTileInfo[] = {']
for (f, w, h), n in zip(foot, names):
    out.append('    {%s, %d, %d},  // %s' % ('true' if f else 'false', w, h, n))
out += ['};', '}  // namespace bic', '']
open(root + '/src/tile_table.hpp', 'w').write('\n'.join(out))

def load(f):
    s = open(f).read()
    w = int(re.search(r' w=.(\d+)', s).group(1)); h = int(re.search(r' h=.(\d+)', s).group(1))
    t = []
    for tok in re.search(r'<t>(.*?)</t>', s, re.S).group(1).split(','):
        if tok:
            a = tok.split(':'); t += [int(a[0])] * (int(a[1]) if len(a) > 1 else 1)
    items = [tuple(map(int, p.split(','))) for p in re.search(r'<i>(.*?)</i>', s, re.S).group(1).split('|') if p.count(',') == 2]
    return w, h, t, items

bad = 0
for f in sorted(glob.glob(root + '/assets/levels/*.xml')):
    w, h, t, items = load(f)
    wall = [False] * (w * h)
    for y in range(h):
        for x in range(w):
            id = t[y * w + x]
            if id >= 32:
                fr, fw, fh = foot[id - 32]
                if not fr:
                    for yy in range(y, min(h, y + fh)):
                        for xx in range(x, min(w, x + fw)): wall[yy * w + xx] = True
    # as células 0 não cobertas por pegada são chão
    p = [(x, y) for ty, x, y in items if ty == 1]
    seen = set(); st = list(p)
    while st:
        c = st.pop()
        if c in seen: continue
        x, y = c
        if not (0 <= x < w and 0 <= y < h) or wall[y * w + x]: continue
        seen.add(c); st += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    miss = [(ty, x, y) for ty, x, y in items if ty not in (28, 29, 30) and (x, y) not in seen]
    onwall = [(ty, x, y) for ty, x, y in items if 0 <= x < w and 0 <= y < h and wall[y * w + x]]
    if miss or onwall:
        bad += 1; print(f.split('/')[-1], 'inalcançáveis:', len(miss), miss[:4], 'em parede:', len(onwall), onwall[:4])
print('fases com problema:', bad)
