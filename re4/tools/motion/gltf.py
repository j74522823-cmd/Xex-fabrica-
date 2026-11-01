"""glTF 2.0 writer for a posed parts hierarchy.

Scene: node "model" (the cModel: root motion) with the parts as a node tree (parent links and
rest translations from the .bin), a skin whose joints are the parts nodes (inverse bind
matrices from the rest pose) and the character's meshes bound to it: one glTF mesh per model .bin
(`MeshSource`: body, head, hands ...), one primitive per ModelPart with POSITION / NORMAL /
TEXCOORD_0 / COLOR_0 / JOINTS_0 / WEIGHTS_0, a material per (texture, alpha texture) with the
PNG written to `textures/` next to the output (shared by the motions of an archive). Without
meshes, a stick-figure mesh (one thin triangle per parts towards its parent) so that importers
create an armature. One animation with translation / rotation / scale samplers per parts node
and per the model node, sampled at every motion frame (frame / fps seconds, LINEAR: exact at the
frame times, which is what the game evaluates), values straight from the game's parts matrices.
Units: the game's millimetres times `scale`.

Skinning follows game/trans.cpp: calcWeightMat builds mtx[k] = parts k world matrix x bind matrix
(inverse rest translation), MakeWeightPalette blends them per Weight entry, CalcSk1_x applies
palette[vertex matrix index] to the rest-pose model-space vertex; that is glTF linear blend
skinning with the inverse bind matrices of the rest pose, so the same skin serves the mesh and the
game's per-part rigid vertices (single-entry weights) become one joint with weight 1.
Triangle winding: the GX order (strips alternate) is counter-clockwise towards the vertex normals
on every disc model checked, so it is kept as glTF's front face.
"""
import base64
import json
import math
import os
import struct

FLOAT = 5126
U32 = 5125
U16 = 5123
U8 = 5121
ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963


def normalize(v):
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v] if n else list(v)


def decompose(l_mat):
    """3x4 row-major (game Mtx) -> translation, columns' lengths (scale), rotation 3x4 with unit columns."""
    m = l_mat
    t = [m[3], m[7], m[11]]
    cols = [[m[0], m[4], m[8]], [m[1], m[5], m[9]], [m[2], m[6], m[10]]]
    sc = [math.sqrt(sum(c * c for c in col)) for col in cols]
    r = [0.0] * 12
    for j in range(3):
        col = normalize(cols[j])
        r[j] = col[0]
        r[4 + j] = col[1]
        r[8 + j] = col[2]
    return t, sc, r


def quat_normalize(q):
    n = math.sqrt(sum(c * c for c in q))
    return [c / n for c in q]


def quat_continuous(prev, q):
    """Flip q to the hemisphere of prev (same rotation, shortest interpolation)."""
    if prev is not None and sum(a * b for a, b in zip(prev, q)) < 0:
        return [-c for c in q]
    return q


def invert_affine(m):
    """Inverse of a 3x4 row-major rigid transform with unit rotation columns (rest pose)."""
    r = [[m[0], m[1], m[2]], [m[4], m[5], m[6]], [m[8], m[9], m[10]]]
    t = [m[3], m[7], m[11]]
    rt = [[r[j][i] for j in range(3)] for i in range(3)]
    it = [-sum(rt[i][j] * t[j] for j in range(3)) for i in range(3)]
    return [rt[0][0], rt[0][1], rt[0][2], it[0], rt[1][0], rt[1][1], rt[1][2], it[1], rt[2][0], rt[2][1], rt[2][2], it[2]]


def col_major_4x4(m34, scale):
    """glTF column-major 4x4 from a 3x4 row-major game matrix (translation scaled)."""
    out = []
    for c in range(4):
        for r in range(3):
            v = m34[4 * r + c]
            out.append(v * scale if c == 3 else v)
        out.append(1.0 if c == 3 else 0.0)
    return out


class Builder:
    def __init__(self):
        self.blob = bytearray()
        self.buffer_views = []
        self.accessors = []

    def accessor(self, fmt, comp_type, type_name, values, target=None, minmax=False, normalized=False):
        st = struct.Struct('<' + fmt)
        n = len(values)
        while len(self.blob) % 4:
            self.blob += b'\0'
        off = len(self.blob)
        for v in values:
            self.blob += st.pack(*v) if isinstance(v, (tuple, list)) else st.pack(v)
        bv = {'buffer': 0, 'byteOffset': off, 'byteLength': len(self.blob) - off}
        if target:
            bv['target'] = target
        self.buffer_views.append(bv)
        acc = {'bufferView': len(self.buffer_views) - 1, 'componentType': comp_type, 'count': n, 'type': type_name}
        if normalized:
            acc['normalized'] = True
        if minmax:
            if isinstance(values[0], (tuple, list)):
                acc['min'] = [min(v[i] for v in values) for i in range(len(values[0]))]
                acc['max'] = [max(v[i] for v in values) for i in range(len(values[0]))]
            else:
                acc['min'] = [min(values)]
                acc['max'] = [max(values)]
        self.accessors.append(acc)
        return len(self.accessors) - 1


def compose_image(textures, tex_id, alpha_id):
    """RGBA8 of model texture tex_id; with alpha_id (ModelPart.alphaTex, flags bit2) the alpha channel
    is that texture's alpha (trans.cpp alphaSetup: GX_CA_TEXA of the alpha texture on the same
    texcoord), nearest-resampled to the base texture's size."""
    import numpy as np
    img = textures[tex_id].decode().copy()
    if alpha_id is not None:
        a = textures[alpha_id].decode()[..., 3]
        h, w = img.shape[:2]
        ys = (np.arange(h) * a.shape[0]) // h
        xs = (np.arange(w) * a.shape[1]) // w
        img[..., 3] = a[ys[:, None], xs[None, :]]
    return img


class MeshSource:
    """One model .bin with its texture palette: mesh (meshbin.Mesh), textures ([gxtex.Texture]),
    label (file stem of the PNGs / glTF mesh name), tex_prefix (PNG name prefix, shared by motions
    of the same archive)."""

    def __init__(self, mesh, textures, label, tex_prefix, role=None):
        self.mesh = mesh
        self.textures = textures
        self.label = label
        self.tex_prefix = tex_prefix
        self.role = role

    def shape_names(self):
        return [f'shape_{k:02d}' for k in range(len(self.mesh.shapes or []))]


def build_mesh(b, src, scale, out_dir, images, textures_out, materials, skin_check):
    """glTF mesh of one .bin: one primitive per ModelPart (its display list, material texId /
    alphaTex), vertices de-duplicated per part on the (position, normal, colour, texcoord) index
    tuple, JOINTS_0 / WEIGHTS_0 from the Weight entry the vertex's matrix index selects
    (meshbin.Mesh.skin: MakeWeightPalette / CalcSk1_x). The shape table (meshbin.Mesh.shapes,
    shape.cpp CalculateShape_new: per key a list of vertex position deltas added to vtxOrig before
    the skinning, normals untouched) becomes one POSITION morph target per key on every primitive,
    named in the mesh's extras.targetNames. Returns (mesh dict, n_vertices, n_triangles, dropped)."""
    from . import gxtex
    m = src.mesh
    prims = []
    n_vert = n_tri = 0
    dropped = [0]
    shape_deltas = [m.shape_deltas(k) for k in range(len(m.shapes or []))]
    for pi, part in enumerate(m.parts):
        tris = part.triangles()
        if not tris:
            continue
        index = {}
        seen = set()
        pos, nrm, uv, clr, joints, weights, idx = [], [], [], [], [], [], []
        for tri in tris:
            if len({v[0] for v in tri}) < 3:
                continue   # degenerate (nothing rasterised)
            face = frozenset(tri)
            if face in seen:
                dropped[0] += 1   # the same face twice (pl00:4 has one); Blender's mesh validation removes it
                continue
            seen.add(face)
            for v in tri:
                k = index.get(v)
                if k is None:
                    k = index[v] = len(pos)
                    pos.append(tuple(c * scale for c in m.position(v[0])))
                    nrm.append(tuple(normalize(m.normal(v[1]))))
                    clr.append(m.colour(v[2]))
                    uv.append(m.texcoord(v[3]))
                    pairs = m.skin(v[0])
                    for j, _ in pairs:
                        skin_check(j)
                    pairs = pairs + [(0, 0.0)] * (4 - len(pairs))
                    joints.append(tuple(j for j, _ in pairs))
                    weights.append(tuple(w for _, w in pairs))
                idx.append(k)
        if not idx:
            continue
        n_vert += len(pos)
        n_tri += len(idx) // 3
        alpha_id = part.alpha_tex if part.flags & 4 else None
        key = (src.tex_prefix, part.tex_id, alpha_id)
        if key not in images:
            fname = f'{src.tex_prefix}_{part.tex_id:02d}' + (f'_a{alpha_id:02d}' if alpha_id is not None else '') + '.png'
            path = os.path.join(out_dir, 'textures', fname)
            if path not in textures_out:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'wb') as f:
                    f.write(gxtex.png(compose_image(src.textures, part.tex_id, alpha_id)))
                textures_out.add(path)
            images[key] = len(materials)
            t = src.textures[part.tex_id]
            mat = {
                'name': f'{src.tex_prefix}_tex{part.tex_id:02d}' + (f'_alpha{alpha_id:02d}' if alpha_id is not None else ''),
                'pbrMetallicRoughness': {'baseColorTexture': {'index': len(materials)}, 'metallicFactor': 0.0, 'roughnessFactor': 1.0},
                'doubleSided': False,
                'extras': {'re4': {'texture': part.tex_id, 'format': t.fmt_name, 'size': [t.width, t.height]}},
            }
            if alpha_id is not None:
                # alphaSetup: GXSetAlphaCompare(GX_GREATER, alphaRef, GX_AOP_OR, GX_GREATER, 0xFF): alpha > alphaRef passes
                mat['alphaMode'] = 'MASK'
                mat['alphaCutoff'] = (part.alpha_ref + 1) / 255.0
            materials.append((mat, 'textures/' + fname))
        prim = {
            'attributes': {
                'POSITION': b.accessor('3f', FLOAT, 'VEC3', pos, ARRAY_BUFFER, minmax=True),
                'NORMAL': b.accessor('3f', FLOAT, 'VEC3', nrm, ARRAY_BUFFER),
                'TEXCOORD_0': b.accessor('2f', FLOAT, 'VEC2', uv, ARRAY_BUFFER),
                'COLOR_0': b.accessor('4B', U8, 'VEC4', clr, ARRAY_BUFFER, normalized=True),
                'JOINTS_0': b.accessor('4H', U16, 'VEC4', joints, ARRAY_BUFFER),
                'WEIGHTS_0': b.accessor('4f', FLOAT, 'VEC4', weights, ARRAY_BUFFER),
            },
            'indices': b.accessor('I', U32, 'SCALAR', idx, ELEMENT_ARRAY_BUFFER),
            'mode': 4,
            'material': images[key],
            'extras': {'re4': {'part': pi, 'flags': part.flags, 'texId': part.tex_id, 'alphaTex': part.alpha_tex,
                               'bumpTex': part.bump_tex, 'nPoly': part.n_poly}},
        }
        if shape_deltas:
            zero = (0.0, 0.0, 0.0)
            prim['targets'] = []
            for deltas in shape_deltas:
                dp = [tuple(c * scale for c in deltas.get(v[0], zero)) for v in index]
                prim['targets'].append({'POSITION': b.accessor('3f', FLOAT, 'VEC3', dp, ARRAY_BUFFER, minmax=True)})
        prims.append(prim)
    mesh = {'name': src.label, 'primitives': prims}
    if shape_deltas:
        mesh['weights'] = [0.0] * len(shape_deltas)
        mesh['extras'] = {'targetNames': src.shape_names()}
    return mesh, n_vert, n_tri, dropped[0]


def export(model, motion, poses, out_path, name, fps=30.0, scale=0.001, root_motion=True, extras=None, meshes=None):
    """poses: evalhost.Pose per frame 0..maxFrame (the game's parts matrices). meshes: [MeshSource]
    skinned to the parts (None: the stick-figure placeholder mesh). Returns (doc, mesh stats)."""
    n = model.n_parts
    b = Builder()
    nodes = []
    # node 0: the model, nodes 1..n: parts
    model_node = {'name': name and f'{name}_model' or 'model', 'children': []}
    nodes.append(model_node)
    for p in model.parts:
        nodes.append({'name': f'parts_{p.no:03d}', 'translation': [c * scale for c in p.pos], 'children': []})
    for p in model.parts:
        parent = 0 if p.parent < 0 else p.parent + 1
        nodes[parent]['children'].append(p.no + 1)
    for nd in nodes:
        if not nd['children']:
            del nd['children']

    # rest pose world matrices (model at the origin) for the inverse bind matrices
    rest_world = [None] * n
    for p in model.parts:
        base = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0] if p.parent < 0 else rest_world[p.parent]
        m = list(base)
        m[3] += p.pos[0]
        m[7] += p.pos[1]
        m[11] += p.pos[2]
        rest_world[p.no] = m
    ibm = [col_major_4x4(invert_affine(m), scale) for m in rest_world]
    ibm_acc = b.accessor('16f', FLOAT, 'MAT4', ibm)
    skin = {'joints': list(range(1, n + 1)), 'inverseBindMatrices': ibm_acc, 'skeleton': 0, 'name': 'skeleton'}

    mesh_list = []
    mesh_nodes = []
    materials = []      # (material dict, image uri)
    stats = {'vertices': 0, 'triangles': 0, 'meshes': 0, 'materials': 0, 'duplicate_faces': 0, 'labels': [], 'shape_keys': {}}
    if meshes:
        out_dir = os.path.dirname(os.path.abspath(out_path))
        images = {}
        textures_out = set()

        def skin_check(j):
            if j >= n:
                raise ValueError(f'mesh weight refers to parts {j}, the skeleton has {n}')
        for src in meshes:
            mesh, nv, nt, dup = build_mesh(b, src, scale, out_dir, images, textures_out, materials, skin_check)
            stats['vertices'] += nv
            stats['triangles'] += nt
            stats['duplicate_faces'] += dup
            stats['labels'].append(src.label)
            if src.mesh.shapes:
                stats['shape_keys'][src.label] = src.shape_names()
            mesh_nodes.append(len(nodes))
            nodes.append({'name': src.label, 'mesh': len(mesh_list), 'skin': 0})
            mesh_list.append(mesh)
        stats['meshes'] = len(mesh_list)
        stats['materials'] = len(materials)
    else:
        # one thin triangle per parts from its rest position to its parent's, skinned to the parts
        pos = []
        joints = []
        weights = []
        idx = []
        for p in model.parts:
            a = [c * scale for c in rest_world[p.no][3::4]]
            pp = [0.0, 0.0, 0.0] if p.parent < 0 else [c * scale for c in rest_world[p.parent][3::4]]
            d = [pp[i] - a[i] for i in range(3)]
            length = math.sqrt(sum(c * c for c in d)) or 0.02 * scale / 0.001
            w = 0.006 * length + 0.002 * scale / 0.001
            side = normalize([-d[1], d[0], 0.0] if abs(d[2]) < 0.9 * length else [0.0, -d[2], d[1]])
            j = p.no
            pj = j if p.parent < 0 else p.parent
            base = len(pos)
            pos += [(a[0] + side[0] * w, a[1] + side[1] * w, a[2] + side[2] * w),
                    (a[0] - side[0] * w, a[1] - side[1] * w, a[2] - side[2] * w),
                    tuple(pp)]
            joints += [(j, 0, 0, 0), (j, 0, 0, 0), (pj, 0, 0, 0)]
            weights += [(1.0, 0.0, 0.0, 0.0)] * 3
            idx += [base, base + 1, base + 2, base, base + 2, base + 1]
        prim = {
            'attributes': {
                'POSITION': b.accessor('3f', FLOAT, 'VEC3', pos, ARRAY_BUFFER, minmax=True),
                'JOINTS_0': b.accessor('4H', U16, 'VEC4', joints, ARRAY_BUFFER),
                'WEIGHTS_0': b.accessor('4f', FLOAT, 'VEC4', weights, ARRAY_BUFFER),
            },
            'indices': b.accessor('H', U16, 'SCALAR', idx, ELEMENT_ARRAY_BUFFER),
            'mode': 4,
        }
        mesh_list.append({'name': 'skeleton_sticks', 'primitives': [prim]})
        mesh_nodes.append(len(nodes))
        nodes.append({'name': 'skeleton_mesh', 'mesh': 0, 'skin': 0})

    # animation
    times = [f / fps for f in range(len(poses))]
    time_acc = b.accessor('f', FLOAT, 'SCALAR', times, minmax=True)
    samplers = []
    channels = []

    def add_channel(node, path, values, fmt, typ):
        acc = b.accessor(fmt, FLOAT, typ, values)
        samplers.append({'input': time_acc, 'output': acc, 'interpolation': 'LINEAR'})
        channels.append({'sampler': len(samplers) - 1, 'target': {'node': node, 'path': path}})

    for i in range(n):
        tr = []
        rot = []
        sc = []
        prev = None
        for pose in poses:
            t, s, r = decompose(pose.l_mat[i])
            q = quat_continuous(prev, quat_normalize(list(pose.quat(r))))
            prev = q
            tr.append(tuple(c * scale for c in t))
            rot.append(tuple(q))
            sc.append(tuple(s))
        add_channel(i + 1, 'translation', tr, '3f', 'VEC3')
        add_channel(i + 1, 'rotation', rot, '4f', 'VEC4')
        if any(abs(c - 1.0) > 1e-6 for s in sc for c in s):
            add_channel(i + 1, 'scale', sc, '3f', 'VEC3')
    if root_motion and (poses[0].root_pos is not None or poses[0].root_rot is not None):
        tr = [tuple(c * scale for c in pose.root_pos) for pose in poses]
        prev = None
        rot = []
        for pose in poses:
            q = quat_continuous(prev, quat_normalize(list(pose.quat(pose.root_mat))))
            prev = q
            rot.append(tuple(q))
        add_channel(0, 'translation', tr, '3f', 'VEC3')
        add_channel(0, 'rotation', rot, '4f', 'VEC4')

    anim = {'name': name or 'motion', 'samplers': samplers, 'channels': channels}
    doc = {
        'asset': {'version': '2.0', 'generator': 're4 tools/motion_export.py'},
        'scene': 0,
        'scenes': [{'nodes': [0] + mesh_nodes}],
        'nodes': nodes,
        'skins': [skin],
        'animations': [anim],
        'accessors': b.accessors,
        'bufferViews': b.buffer_views,
        'meshes': mesh_list,
    }
    if materials:
        doc['images'] = [{'uri': uri} for _, uri in materials]
        doc['samplers'] = [{'magFilter': 9729, 'minFilter': 9729, 'wrapS': 10497, 'wrapT': 10497}]   # GX_REPEAT (TEXHeader wrapS/T = 1)
        doc['textures'] = [{'source': i, 'sampler': 0} for i in range(len(materials))]
        doc['materials'] = [mat for mat, _ in materials]
    if extras:
        doc['extras'] = extras
    write(doc, bytes(b.blob), out_path)
    return doc, stats


def write(doc, blob, out_path):
    while len(blob) % 4:
        blob += b'\0'
    if out_path.lower().endswith('.glb'):
        doc['buffers'] = [{'byteLength': len(blob)}]
        js = json.dumps(doc, separators=(',', ':')).encode()
        while len(js) % 4:
            js += b' '
        total = 12 + 8 + len(js) + 8 + len(blob)
        with open(out_path, 'wb') as f:
            f.write(struct.pack('<III', 0x46546C67, 2, total))
            f.write(struct.pack('<II', len(js), 0x4E4F534A) + js)
            f.write(struct.pack('<II', len(blob), 0x004E4942) + blob)
    else:
        doc['buffers'] = [{'byteLength': len(blob), 'uri': 'data:application/octet-stream;base64,' + base64.b64encode(blob).decode()}]
        with open(out_path, 'w') as f:
            json.dump(doc, f, separators=(',', ':'))
