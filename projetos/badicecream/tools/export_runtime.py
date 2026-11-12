"""Gera runtime/ (o que o executável lê em game:\\ no Xbox 360):
  atlas.txt, atlasN.argb (bytes A,R,G,B = uint32 0xAARRGGBB em big-endian), levels/levelNN.xml, snd/*.s16 (PCM s16 big-endian, mono, 48 kHz), snd.txt
Uso: python3 -I tools/export_runtime.py <raiz do projeto> <saida>"""
import json, os, shutil, subprocess, sys
import numpy as np
from PIL import Image
root, out = sys.argv[1], sys.argv[2]
os.makedirs(out + '/levels', exist_ok=True); os.makedirs(out + '/snd', exist_ok=True)
atlas = json.load(open(root + '/assets/atlas/atlas.json'))
pages = sorted({f['p'] for an in atlas.values() for fr in an.values() for f in fr})
lines = ['pages %d' % len(pages)]
for p in pages:
    im = Image.open('%s/assets/atlas/atlas%d.png' % (root, p)).convert('RGBA')
    a = np.asarray(im)[..., [3, 0, 1, 2]]
    open('%s/atlas%d.argb' % (out, p), 'wb').write(a.tobytes())
    lines.append('page %d %d %d atlas%d.argb' % (p, im.width, im.height, p))
n = 0
for cls in sorted(atlas):
    for anim, frs in atlas[cls].items():
        for i, f in enumerate(frs):
            lines.append('F %s %s %d %d %d %d %d %d %d %d' % (cls, anim, i, f['p'], f['x'], f['y'], f['w'], f['h'], f['ox'], f['oy'])); n += 1
open(out + '/atlas.txt', 'w').write('\n'.join(lines) + '\n')
for f in sorted(os.listdir(root + '/assets/levels')):
    shutil.copy(root + '/assets/levels/' + f, out + '/levels/' + f)
# Sons: o arquivo é o id do clipe - 1 (ex.: ice_wall_312 = símbolo 4276 -> som 4275). Nomes vindos de playSound() no bytecode.
sfx = {'ice_cream_hurt': 4273, 'ice_wall': 4275, 'ice_wall_destroy': 4277, 'icecream_breath_in': 4279, 'icecream_breath_out': 4281,
       'icecream_kick': 4283, 'log_roll_hit': 4285, 'pick_up_fruit': 4287, 'select': 4289, 'squid_electric': 4291,
       'squid_ground_pound': 4293, 'squid_slap': 4295, 'change_flower': 4297, 'cherry_transport': 4299, 'directional_tile': 4301,
       'duck': 4303, 'flametile': 4305, 'pineapple': 4307, 'menupopup': 4309, 'transition': 4311, 'nitrome': 4313, 'endlevel': 4315,
       'music_menu': 5093, 'music_game': 5094, 'music_win': 5095, 'music_lose': 5096}
snd = []
for name, sid in sfx.items():
    dst = '%s/snd/%s.s16' % (out, name)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', '%s/assets/snd/%d.mp3' % (root, sid), '-f', 's16be', '-ar', '48000', '-ac', '1', dst], check=True)
    snd.append('%s snd/%s.s16 %d %d' % (name, name, os.path.getsize(dst) // 2, 1 if name.startswith('music_') and name != 'music_win' and name != 'music_lose' else 0))
open(out + '/snd.txt', 'w').write('\n'.join(snd) + '\n')
print('quadros', n, 'sons', len(snd))
