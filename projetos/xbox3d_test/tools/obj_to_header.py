#!/usr/bin/env python3
"""Convert a small Wavefront OBJ mesh into a C header for the XSDK build.

Supported input: v records and polygonal f records (v, v/vt, v//vn, v/vt/vn).
Polygons are fan-triangulated. Materials, UVs and normals are intentionally
ignored in this first Xbox 360 importer; the runtime shader supplies tint.
"""
import pathlib
import sys

MAX_VERTICES = 4096
MAX_TRIANGLES = 8192

def parse_index(token, count, line_no):
    raw = token.split("/", 1)[0]
    if not raw:
        raise ValueError(f"line {line_no}: face corner has no position index")
    index = int(raw)
    resolved = index - 1 if index > 0 else count + index
    if resolved < 0 or resolved >= count:
        raise ValueError(f"line {line_no}: vertex index {index} is out of range")
    return resolved

def convert(source, output):
    positions = []
    triangles = []
    for line_no, raw_line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.partition("#")[0].strip()
        if not line:
            continue
        parts = line.split()
        if parts[0] == "v":
            if len(parts) < 4:
                raise ValueError(f"line {line_no}: expected v x y z")
            positions.append(tuple(float(v) for v in parts[1:4]))
            if len(positions) > MAX_VERTICES:
                raise ValueError("OBJ exceeds vertex safety limit")
        elif parts[0] == "f":
            if len(parts) < 4:
                raise ValueError(f"line {line_no}: face needs at least 3 corners")
            face = [parse_index(token, len(positions), line_no) for token in parts[1:]]
            for i in range(1, len(face) - 1):
                triangles.append((face[0], face[i], face[i + 1]))
                if len(triangles) > MAX_TRIANGLES:
                    raise ValueError("OBJ exceeds triangle safety limit")
    if not positions or not triangles:
        raise ValueError("OBJ must contain at least one vertex and one face")
    expanded = [positions[index] for tri in triangles for index in tri]
    if len(expanded) > 65535:
        raise ValueError("expanded OBJ exceeds 16-bit index range")
    lines = [
        "/* Generated from assets/player_lowpoly.obj; do not edit by hand. */",
        "#ifndef XBOX3D_PLAYER_OBJ_H",
        "#define XBOX3D_PLAYER_OBJ_H",
        "#include <stdint.h>",
        f"#define PLAYER_OBJ_VERTEX_COUNT {len(expanded)}u",
        f"#define PLAYER_OBJ_INDEX_COUNT {len(expanded)}u",
        "static const float player_obj_vertices[PLAYER_OBJ_VERTEX_COUNT][6] = {",
    ]
    for x, y, z in expanded:
        lines.append(f"    {{{x:.6f}f, {y:.6f}f, {z:.6f}f, 1.0f, 1.0f, 1.0f}},")
    lines.extend(["};", "static const uint16_t player_obj_indices[PLAYER_OBJ_INDEX_COUNT] = {"])
    for start in range(0, len(expanded), 12):
        values = ", ".join(str(i) for i in range(start, min(start + 12, len(expanded))))
        lines.append("    " + values + ",")
    lines.extend(["};", "#endif", ""])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"OBJ import: {len(positions)} source vertices, {len(triangles)} triangles")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: obj_to_header.py input.obj output.h")
    try:
        convert(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
    except (OSError, ValueError) as error:
        raise SystemExit(f"OBJ import failed: {error}")
