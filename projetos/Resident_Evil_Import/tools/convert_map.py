#!/usr/bin/env python3
"""
convert_map.py - converte um mapa .glb (glTF 2.0) para o formato binario do jogo (.rfm).

Uso:
    python3 tools/convert_map.py mapa.glb saida.rfm [--root Granja] [--max-tex 512]

O que ele faz:
  * percorre a cena a partir do no --root (padrao: o primeiro no raiz que tiver malhas
    e nao for um personagem), aplicando as transformacoes de cada no;
  * junta todos os triangulos que usam a mesma textura em um unico "lote" (batch),
    para o console fazer poucos draws por quadro (o mapa tem 274 materiais e 51 texturas);
  * grava texturas em ARGB8 com mipmaps, ja na ordem de bytes do Xbox 360 (big-endian).

Formato .rfm (tudo big-endian):
  Cabecalho (64 bytes):
    char[4] magic = "RFM1"
    u32 version = 1
    u32 num_textures, num_batches, num_vertices, num_indices
    f32 bounds_min[3], bounds_max[3]
    u32 reservado[6]
  Tabela de texturas (16 bytes cada): u16 w, u16 h, u16 levels, u16 pad, u32 offset, u32 size
  Tabela de lotes   (16 bytes cada): u32 texture, u32 first_index, u32 index_count, u32 flags
  Vertices (32 bytes cada): f32 pos[3], f32 normal[3], f32 uv[2]
  Indices: u32
  Dados das texturas: ARGB8, nivel 0 primeiro, depois cada mip.

So usa a biblioteca padrao do Python, numpy e Pillow.
"""
import argparse
import io
import json
import struct
import sys

import numpy as np
from PIL import Image

COMPONENT_DTYPE = {5120: np.int8, 5121: np.uint8, 5122: np.int16,
                   5123: np.uint16, 5125: np.uint32, 5126: np.float32}
TYPE_COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

# Nos que nao fazem parte do cenario (personagens, UI, camera da cena original).
SKIP_NAME_PREFIXES = ("Ganado", "mixamorig", "vThirdPersonCamera", "AimCanvas",
                      "vUI", "vGameController", "EventSystem", "Directional Light")


def load_glb(path):
    data = open(path, "rb").read()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2:
        sys.exit("arquivo nao e um .glb glTF 2.0")
    off = 12
    gltf, binchunk = None, b""
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            gltf = json.loads(chunk)
        elif ctype == 0x004E4942:
            binchunk = chunk
        off += 8 + clen
    return gltf, binchunk


def read_accessor(g, binchunk, idx):
    acc = g["accessors"][idx]
    bv = g["bufferViews"][acc["bufferView"]]
    dtype = np.dtype(COMPONENT_DTYPE[acc["componentType"]])
    ncomp = TYPE_COUNT[acc["type"]]
    count = acc["count"]
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride", 0) or dtype.itemsize * ncomp
    raw = np.frombuffer(binchunk, dtype=np.uint8, count=stride * (count - 1) + dtype.itemsize * ncomp,
                        offset=start)
    if stride == dtype.itemsize * ncomp:
        arr = raw.view(dtype).reshape(count, ncomp)
    else:
        arr = np.lib.stride_tricks.as_strided(raw, shape=(count, ncomp * dtype.itemsize),
                                              strides=(stride, 1)).copy().view(dtype).reshape(count, ncomp)
    arr = arr.astype(np.float32) if dtype != np.uint32 and acc["type"] != "SCALAR" else arr
    if acc.get("normalized") and dtype.kind in "iu":
        arr = arr.astype(np.float32) / float(np.iinfo(dtype).max)
    return arr


def node_matrix(n):
    if "matrix" in n:
        return np.array(n["matrix"], dtype=np.float64).reshape(4, 4).T
    t = np.array(n.get("translation", [0, 0, 0]), dtype=np.float64)
    x, y, z, w = n.get("rotation", [0, 0, 0, 1])
    s = np.array(n.get("scale", [1, 1, 1]), dtype=np.float64)
    r = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    m = np.eye(4)
    m[:3, :3] = r * s
    m[:3, 3] = t
    return m


def has_mesh(g, ni):
    n = g["nodes"][ni]
    if n.get("name", "").startswith(SKIP_NAME_PREFIXES):
        return False
    return "mesh" in n or any(has_mesh(g, c) for c in n.get("children", []))


def pick_root(g, wanted):
    roots = g["scenes"][g.get("scene", 0)]["nodes"]
    if wanted:
        for r in roots:
            if g["nodes"][r].get("name") == wanted:
                return [r]
        sys.exit(f"no raiz '{wanted}' nao encontrado; raizes: "
                 + ", ".join(g["nodes"][r].get("name", "?") for r in roots))
    return [r for r in roots if has_mesh(g, r)]


def image_for_material(g, mat_index):
    if mat_index is None:
        return None
    mat = g["materials"][mat_index]
    tex = mat.get("pbrMetallicRoughness", {}).get("baseColorTexture")
    if tex is None:
        return None
    return g["textures"][tex["index"]].get("source")


def decode_image(g, binchunk, img_index, max_size):
    img = g["images"][img_index]
    bv = g["bufferViews"][img["bufferView"]]
    start = bv.get("byteOffset", 0)
    im = Image.open(io.BytesIO(binchunk[start:start + bv["byteLength"]])).convert("RGBA")
    w, h = im.size
    # lado em potencia de 2, limitado a max_size
    def p2(v):
        p = 1
        while p * 2 <= v:
            p *= 2
        return min(max(p, 4), max_size)
    nw, nh = p2(w), p2(h)
    if (nw, nh) != (w, h):
        im = im.resize((nw, nh), Image.LANCZOS)
    return im


def argb_mips(im):
    levels = []
    cur = im
    while True:
        a = np.asarray(cur, dtype=np.uint8)            # RGBA
        argb = a[..., [3, 0, 1, 2]].copy()              # A R G B, ordem de bytes do 360
        levels.append(argb.tobytes())
        w, h = cur.size
        if w <= 4 or h <= 4:
            break
        cur = cur.resize((max(w // 2, 1), max(h // 2, 1)), Image.BOX)
    return levels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glb")
    ap.add_argument("out")
    ap.add_argument("--root", help="nome do no raiz do cenario (ex.: Granja)")
    ap.add_argument("--max-tex", type=int, default=512, help="lado maximo das texturas")
    ap.add_argument("--keep-all", action="store_true", help="nao pular personagens/UI")
    args = ap.parse_args()

    g, binchunk = load_glb(args.glb)
    roots = pick_root(g, args.root)

    # lotes: chave = indice da imagem (None = sem textura)
    batches = {}   # img -> lista de (pos, nrm, uv, idx)

    def visit(ni, parent):
        n = g["nodes"][ni]
        if not args.keep_all and n.get("name", "").startswith(SKIP_NAME_PREFIXES):
            return
        world = parent @ node_matrix(n)
        if "mesh" in n:
            m3 = world[:3, :3]
            nmat = np.linalg.inv(m3).T
            flip = np.linalg.det(m3) < 0
            for prim in g["meshes"][n["mesh"]]["primitives"]:
                if prim.get("mode", 4) != 4:
                    continue
                at = prim["attributes"]
                pos = read_accessor(g, binchunk, at["POSITION"]).astype(np.float64)
                cnt = len(pos)
                nrm = (read_accessor(g, binchunk, at["NORMAL"]).astype(np.float64)
                       if "NORMAL" in at else np.tile([0.0, 1.0, 0.0], (cnt, 1)))
                uv = (read_accessor(g, binchunk, at["TEXCOORD_0"]).astype(np.float64)
                      if "TEXCOORD_0" in at else np.zeros((cnt, 2)))
                idx = (read_accessor(g, binchunk, prim["indices"]).reshape(-1).astype(np.uint32)
                       if "indices" in prim else np.arange(cnt, dtype=np.uint32))
                pos = pos @ world[:3, :3].T + world[:3, 3]
                nrm = nrm @ nmat.T
                nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-8)
                tri = idx.reshape(-1, 3)
                if flip:
                    tri = tri[:, [0, 2, 1]]
                key = image_for_material(g, prim.get("material"))
                batches.setdefault(key, []).append((pos, nrm, uv, tri))
        for c in n.get("children", []):
            visit(c, world)

    for r in roots:
        visit(r, np.eye(4))

    if not batches:
        sys.exit("nenhuma malha encontrada")

    # texturas usadas -> indice local; lote sem textura usa uma textura branca 4x4
    keys = sorted(batches.keys(), key=lambda k: (k is None, k if k is not None else 0))
    tex_images = []
    for k in keys:
        if k is None:
            tex_images.append(Image.new("RGBA", (4, 4), (255, 255, 255, 255)))
        else:
            tex_images.append(decode_image(g, binchunk, k, args.max_tex))

    all_pos, all_nrm, all_uv, all_idx, batch_table = [], [], [], [], []
    vbase = 0
    ibase = 0
    for ti, k in enumerate(keys):
        bidx = []
        for pos, nrm, uv, tri in batches[k]:
            all_pos.append(pos); all_nrm.append(nrm); all_uv.append(uv)
            bidx.append(tri.reshape(-1) + vbase)
            vbase += len(pos)
        bidx = np.concatenate(bidx).astype(np.uint32)
        all_idx.append(bidx)
        batch_table.append((ti, ibase, len(bidx), 0))
        ibase += len(bidx)

    P = np.concatenate(all_pos).astype(np.float32)
    N = np.concatenate(all_nrm).astype(np.float32)
    U = np.concatenate(all_uv).astype(np.float32)
    I = np.concatenate(all_idx).astype(np.uint32)
    verts = np.concatenate([P, N, U], axis=1).astype(">f4")
    bmin, bmax = P.min(axis=0), P.max(axis=0)

    tex_levels = [argb_mips(im) for im in tex_images]

    nt, nb = len(tex_images), len(batch_table)
    header_size = 64
    tex_table_off = header_size
    batch_table_off = tex_table_off + 16 * nt
    vert_off = batch_table_off + 16 * nb
    idx_off = vert_off + verts.nbytes
    tex_data_off = idx_off + I.nbytes
    tex_data_off = (tex_data_off + 4095) & ~4095

    out = bytearray()
    out += struct.pack(">4sIIIII", b"RFM1", 1, nt, nb, len(P), len(I))
    out += struct.pack(">3f3f", *bmin, *bmax)
    out += b"\0" * (header_size - len(out))
    cur = tex_data_off
    tex_blobs = []
    for im, lv in zip(tex_images, tex_levels):
        blob = b"".join(lv)
        out += struct.pack(">HHHHII", im.size[0], im.size[1], len(lv), 0, cur, len(blob))
        tex_blobs.append(blob)
        cur += (len(blob) + 4095) & ~4095
    for b in batch_table:
        out += struct.pack(">IIII", *b)
    out += verts.tobytes()
    out += I.astype(">u4").tobytes()
    out += b"\0" * (tex_data_off - len(out))
    for blob in tex_blobs:
        out += blob
        out += b"\0" * (((len(blob) + 4095) & ~4095) - len(blob))

    open(args.out, "wb").write(out)
    print(f"ok: {args.out}")
    print(f"  texturas: {nt}, lotes (draws): {nb}")
    print(f"  vertices: {len(P)}, triangulos: {len(I) // 3}")
    print(f"  limites: min {np.round(bmin, 2).tolist()}  max {np.round(bmax, 2).tolist()}")
    print(f"  tamanho do arquivo: {len(out) / 1048576:.2f} MB")


if __name__ == "__main__":
    main()
