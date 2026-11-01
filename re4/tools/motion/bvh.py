"""BVH writer: the parts hierarchy with OFFSET = rest position, every joint with 6 channels
(Xposition Yposition Zposition Zrotation Yrotation Xrotation, absolute local translation and the
game's Euler convention RotMatrix = Rz * Ry * Rx, degrees), one MOTION frame per motion frame.
The ROOT is the model node carrying the root motion keys. Scale does not survive BVH (dropped).
"""
import math


def euler_zyx(r):
    """Angles (x, y, z) with RotMatrix(x, y, z) == r (3x4 row-major, unit columns)."""
    sy = -r[8]
    sy = max(-1.0, min(1.0, sy))
    y = math.asin(sy)
    if abs(r[8]) < 0.999999:
        x = math.atan2(r[9], r[10])
        z = math.atan2(r[4], r[0])
    else:
        x = 0.0
        z = math.atan2(-r[1], r[5])
    return x, y, z


def export(model, poses, out_path, fps=30.0, scale=0.001, name='model'):
    from .gltf import decompose
    n = model.n_parts
    children = {i: [] for i in range(-1, n)}
    for p in model.parts:
        children[p.parent].append(p.no)
    lines = ['HIERARCHY']

    def joint(i, depth):
        ind = '  ' * depth
        p = model.parts[i]
        lines.append(f'{ind}JOINT parts_{i:03d}')
        lines.append(f'{ind}{{')
        lines.append(f'{ind}  OFFSET {p.pos[0] * scale:.6f} {p.pos[1] * scale:.6f} {p.pos[2] * scale:.6f}')
        lines.append(f'{ind}  CHANNELS 6 Xposition Yposition Zposition Zrotation Yrotation Xrotation')
        if children[i]:
            for c in children[i]:
                joint(c, depth + 1)
        else:
            lines.append(f'{ind}  End Site')
            lines.append(f'{ind}  {{')
            lines.append(f'{ind}    OFFSET 0.0 {0.05 * scale / 0.001:.6f} 0.0')
            lines.append(f'{ind}  }}')
        lines.append(f'{ind}}}')

    lines.append(f'ROOT {name}')
    lines.append('{')
    lines.append('  OFFSET 0.0 0.0 0.0')
    lines.append('  CHANNELS 6 Xposition Yposition Zposition Zrotation Yrotation Xrotation')
    for c in children[-1]:
        joint(c, 1)
    lines.append('}')
    lines.append('MOTION')
    lines.append(f'Frames: {len(poses)}')
    lines.append(f'Frame Time: {1.0 / fps:.6f}')

    order = []

    def walk(i):
        order.append(i)
        for c in children[i]:
            walk(c)

    for c in children[-1]:
        walk(c)
    for pose in poses:
        vals = []
        rx, ry, rz = pose.root_rot
        vals += [c * scale for c in pose.root_pos] + [math.degrees(rz), math.degrees(ry), math.degrees(rx)]
        for i in order:
            t, s, r = decompose(pose.l_mat[i])
            x, y, z = euler_zyx(r)
            vals += [c * scale for c in t] + [math.degrees(z), math.degrees(y), math.degrees(x)]
        lines.append(' '.join(f'{v:.6f}' for v in vals))
    with open(out_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
