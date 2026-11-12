"""Gera atlas.png (RGBA) + atlas.json a partir do SWF resolvido. Uso: bake_atlas.py sprites.json assets/img saida_dir
Cada classe vira {label: [frames]}; frame = {x,y,w,h,ox,oy} (ox,oy = onde fica a origem do clip dentro do recorte)."""
import sys, json, os, re
from PIL import Image

J = json.load(open(sys.argv[1])); IMG = sys.argv[2]; OUT = sys.argv[3]
os.makedirs(OUT, exist_ok=True)
SP = J['sprites']; SH = J['shapes']
sym = {v: int(k) for k, v in J['symbols'].items()}
_img = {}
def bmp(i):
    if i not in _img: _img[i] = Image.open(f'{IMG}/{i}.png').convert('RGBA')
    return _img[i]
def mul(m, n):  # m depois n: aplica n primeiro, em seguida m
    a, b, c, d, e, f = m; A, B, C, D, E, F = n
    return [a*A + c*B, b*A + d*B, a*C + c*D, b*C + d*D, a*E + c*F + e, b*E + d*F + f]
# matriz guardada como [sx, b, c, sy, tx, ty] com x' = sx*x + c*y + tx ; y' = b*x + sy*y + ty
def mat6(m): return m
CS = 640; OR = CS // 2
def render(cid, t, m, canvas, depth=0):
    key = str(cid)
    if key in SH:
        for bid, fm in SH[key]:
            if bid == 65535: continue
            full = mul(m, fm)  # bitmap px -> twips-ish: fm escala 20 = 1px
            s = 1 / 20.0
            # fm aplica ao espaço do bitmap em twips (px*20), então px bitmap -> *20 -> fm... fm[0]=20 => 1px
            a, b, c, d, e, f = full
            a, b, c, d = a / 1, b, c, d
            # com fm=[20,0,0,20,tx,ty] e m=identidade: x_dest = 20*x_bmp (em twips) => dividir por 20 para px
            M = [a / 20.0 * 1.0, b / 20.0, c / 20.0, d / 20.0, e, f]
            M = [full[0] / 20.0, full[1] / 20.0, full[2] / 20.0, full[3] / 20.0, full[4], full[5]]
            det = M[0] * M[3] - M[2] * M[1]
            if abs(det) < 1e-9: continue
            ia, ib, ic, id_ = M[3] / det, -M[1] / det, -M[2] / det, M[0] / det
            # inversa: de destino (X-OR) para origem bitmap
            tx, ty = M[4] + OR, M[5] + OR
            ie = -(ia * tx + ic * ty); if_ = -(ib * tx + id_ * ty)
            im = bmp(bid)
            layer = im.transform((CS, CS), Image.AFFINE, (ia, ic, ie, ib, id_, if_), resample=Image.NEAREST)
            canvas.alpha_composite(layer)
    elif key in SP and depth < 8:
        fr = SP[key]['frames']
        if not fr: return
        for o in fr[t % len(fr)]:
            if o['id'] is None: continue
            render(o['id'], t, mul(m, o['m']), canvas, depth + 1)
def nested_len(cid, fi, depth=0):
    n = 1
    fr = SP.get(str(cid), {}).get('frames', [])
    if not fr or depth > 6: return 1
    for o in fr[fi % len(fr)]:
        if o['id'] is None: continue
        s = SP.get(str(o['id']))
        if s: n = max(n, len(s['frames']), nested_len(o['id'], 0, depth + 1))
    return n
def anim_frames(cid):
    s = SP[str(cid)]; fr = s['frames']; labs = sorted(s['labels'].items(), key=lambda kv: kv[1])
    out = {}
    if not labs: labs = [('_', 0)]
    for i, (name, start) in enumerate(labs):
        end = labs[i + 1][1] if i + 1 < len(labs) else len(fr)
        rng = list(range(start, max(end, start + 1)))
        if len(rng) == 1: n = min(nested_len(cid, start), 48)
        else: n = len(rng)
        out[name] = [(rng[k % len(rng)] if len(rng) > 1 else rng[0], k) for k in range(n)]
    return out
WANT = re.compile(r'^(com\.nitrome\.badicecream\.|BlockTile|LandTile|Player|Collectible|.*Enemy|Big|Brick|Four|One|Two|Hut|Igloo|Large|Log|Med|Melted|Side|Small|Snow|Stones|Striped|Pole|Smoke|Cubed|Little|Campfire|Ice|Break|Flame)')
SKIP = re.compile(r'(Button|Font|Text|Score|Letter|Popup|Overlay|Transition|Load|Menu|Selection|Board|Panel|Line|TextBox|SimpleButton|__)')
items = []  # (nome, anim, quadros PIL)
for name, cid in sorted(sym.items()):
    if not WANT.match(name) or SKIP.search(name) or str(cid) not in SP: continue
    for an, frs in anim_frames(cid).items():
        pil = []
        for fi, t in frs:
            c = Image.new('RGBA', (CS, CS), (0, 0, 0, 0))
            fr = SP[str(cid)]['frames']
            for o in fr[fi % len(fr)]:
                if o['id'] is not None: render(o['id'], t, o['m'], c)
            bb = c.getbbox()
            pil.append((c.crop(bb), bb) if bb else (None, None))
        items.append((name.split('.')[-1], an, pil))
# empacotamento "shelf", com páginas de 2048x2048 e quadros idênticos compartilhados
AW = AH = 2048; x = y = rowh = 0; pages = [Image.new('RGBA', (AW, AH), (0, 0, 0, 0))]; man = {}; seen = {}
for name, an, frs in items:
    lst = []
    for im, bb in frs:
        if im is None: lst.append(dict(p=0, x=0, y=0, w=0, h=0, ox=0, oy=0)); continue
        w, h = im.size; key = (w, h, im.tobytes(), OR - bb[0], OR - bb[1])
        if key in seen: lst.append(seen[key]); continue
        if x + w + 1 > AW: x = 0; y += rowh + 1; rowh = 0
        if y + h + 1 > AH: pages.append(Image.new('RGBA', (AW, AH), (0, 0, 0, 0))); x = y = rowh = 0
        pages[-1].paste(im, (x, y))
        e = dict(p=len(pages) - 1, x=x, y=y, w=w, h=h, ox=OR - bb[0], oy=OR - bb[1]); seen[key] = e; lst.append(e)
        x += w + 1; rowh = max(rowh, h)
    man.setdefault(name, {})[an] = lst
for i, pg in enumerate(pages): pg.save(f'{OUT}/atlas{i}.png')
json.dump(man, open(f'{OUT}/atlas.json', 'w'), separators=(',', ':'))
print(len(man), 'classes', sum(len(v) for v in man.values()), 'animações', len(pages), 'páginas', len(seen), 'quadros únicos')
