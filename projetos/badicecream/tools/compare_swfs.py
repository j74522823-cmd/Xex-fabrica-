#!/usr/bin/env python3
"""Compare two Bad Ice-Cream SWF files and extract their DoABC blocks.

Usage:
  python3 compare_swfs.py Bad-Ice-Cream.swf bad_ice_cream_2.swf --out swf_analysis

Uses only the Python standard library. It does not decompile ActionScript;
it extracts the exact DoABC payloads so abc_dump.py can inspect them next.
"""
from __future__ import annotations
import argparse
import collections
import json
import pathlib
import struct
import zlib


def read_swf(path: pathlib.Path):
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:3] not in (b"FWS", b"CWS", b"ZWS"):
        raise ValueError(f"{path}: unsupported or invalid SWF header")
    signature, version = raw[:3], raw[3]
    if signature == b"CWS":
        body = zlib.decompress(raw[8:])
    elif signature == b"FWS":
        body = raw[8:]
    else:
        raise ValueError("LZMA-compressed ZWS is not supported by this standard-library tool")
    declared = struct.unpack_from("<I", raw, 4)[0]
    # RECT starts with Nbits in the upper five bits of the first byte.
    nbits = body[0] >> 3
    rect_bytes = (5 + 4 * nbits + 7) // 8
    frame_rate_raw, frame_count = struct.unpack_from("<HH", body, rect_bytes)
    offset = rect_bytes + 4
    tags = collections.Counter()
    symbols: dict[str, int] = {}
    abc_blocks = []
    sprite_count = 0
    bitmap_count = 0
    sound_count = 0
    tag_list = []
    while offset + 2 <= len(body):
        header = struct.unpack_from("<H", body, offset)[0]
        offset += 2
        code, length = header >> 6, header & 0x3F
        if length == 0x3F:
            if offset + 4 > len(body):
                raise ValueError(f"{path}: truncated long tag header")
            length = struct.unpack_from("<I", body, offset)[0]
            offset += 4
        if offset + length > len(body):
            raise ValueError(f"{path}: tag {code} exceeds file boundary")
        payload = body[offset:offset + length]
        offset += length
        tags[code] += 1
        tag_list.append(code)
        if code == 76:  # SymbolClass
            count = struct.unpack_from("<H", payload)[0]
            p = 2
            for _ in range(count):
                char_id = struct.unpack_from("<H", payload, p)[0]
                p += 2
                end = payload.index(b"\0", p)
                name = payload[p:end].decode("utf-8", "replace")
                p = end + 1
                if name:
                    symbols[name] = char_id
        elif code in (72, 82):  # DoABC / DoABC2
            if code == 82:
                if len(payload) < 5:
                    continue
                flags = struct.unpack_from("<I", payload)[0]
                end = payload.index(b"\0", 4)
                name = payload[4:end].decode("utf-8", "replace")
                abc = payload[end + 1:]
                abc_blocks.append({"tag": code, "flags": flags, "name": name, "bytes": len(abc), "payload": payload})
            else:
                # DoABC has a name string followed by the ABC data.
                end = payload.index(b"\0")
                name = payload[:end].decode("utf-8", "replace")
                abc_blocks.append({"tag": code, "flags": 0, "name": name, "bytes": len(payload) - end - 1, "payload": payload})
        elif code == 39:  # DefineSprite
            sprite_count += 1
        elif code in (20, 21, 35, 36):
            bitmap_count += 1
        elif code == 14:
            sound_count += 1
        if code == 0:  # End
            break
    return {
        "file": path.name,
        "signature": signature.decode(),
        "version": version,
        "compressed_bytes": len(raw),
        "declared_uncompressed_bytes": declared,
        "actual_uncompressed_bytes": len(body) + 8,
        "frame_rate": frame_rate_raw / 256.0,
        "frame_count": frame_count,
        "symbol_count": len(symbols),
        "symbols": symbols,
        "tag_counts": dict(sorted(tags.items())),
        "define_sprite_count": sprite_count,
        "bitmap_definition_count": bitmap_count,
        "define_sound_count": sound_count,
        "abc_blocks": abc_blocks,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("swf1", type=pathlib.Path)
    ap.add_argument("swf2", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("swf_analysis"))
    args = ap.parse_args()
    a, b = read_swf(args.swf1), read_swf(args.swf2)
    args.out.mkdir(parents=True, exist_ok=True)
    for label, item in (("game1", a), ("game2", b)):
        for i, block in enumerate(item["abc_blocks"]):
            (args.out / f"{label}_{i:02d}.abc").write_bytes(block["payload"])
        item["abc_blocks"] = [{k: v for k, v in block.items() if k != "payload"} for block in item["abc_blocks"]]
    common = sorted(set(a["symbols"]) & set(b["symbols"]))
    only_a = sorted(set(a["symbols"]) - set(b["symbols"]))
    only_b = sorted(set(b["symbols"]) - set(a["symbols"]))
    result = {
        "game1": {k: v for k, v in a.items() if k != "symbols"},
        "game2": {k: v for k, v in b.items() if k != "symbols"},
        "shared_symbol_count": len(common),
        "game1_only_symbol_count": len(only_a),
        "game2_only_symbol_count": len(only_b),
        "shared_symbols": common,
        "game1_only_symbols": only_a,
        "game2_only_symbols": only_b,
    }
    (args.out / "comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = ["# Bad Ice-Cream SWF comparison", "", "| Metric | Game 1 | Game 2 |", "|---|---:|---:|"]
    for key, title in (("compressed_bytes", "Compressed bytes"), ("declared_uncompressed_bytes", "Uncompressed bytes"), ("version", "SWF version"), ("frame_rate", "Frame rate"), ("frame_count", "Root frames"), ("symbol_count", "Exported symbols"), ("define_sprite_count", "DefineSprite tags"), ("bitmap_definition_count", "Bitmap definitions"), ("define_sound_count", "DefineSound tags")):
        lines.append(f"| {title} | {a[key]} | {b[key]} |")
    lines += ["", f"Shared SymbolClass names: **{len(common)}**", f"Game 1 only: **{len(only_a)}**", f"Game 2 only: **{len(only_b)}**", "", "## Shared names", ""]
    lines += [f"- `{name}`" for name in common]
    lines += ["", "## Interpretation", "", "Matching SymbolClass names are candidates for shared assets or APIs; they do not prove identical timelines, bytecode, or behavior. Compare the extracted ABC blocks and referenced character definitions before sharing implementation.", "", "## Extracted ActionScript blocks", ""]
    for game, item in (("Game 1", a), ("Game 2", b)):
        lines.append(f"### {game}")
        for i, block in enumerate(item["abc_blocks"]):
            lines.append(f"- `{game.lower().replace(' ', '')}_{i:02d}.abc`: DoABC tag {block['tag']}, name `{block['name']}`, {block['bytes']} bytes")
        lines.append("")
    (args.out / "comparison.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Shared symbols: {len(common)}")
    print(f"Game 1 only: {len(only_a)}; Game 2 only: {len(only_b)}")
    print(f"Extracted ABC blocks and reports to: {args.out}")


if __name__ == "__main__":
    main()
