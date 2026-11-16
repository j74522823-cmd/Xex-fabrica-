#!/usr/bin/env python3
"""Scan a raw big-endian PPC32 code slice for direct branches to a VA.

Usage: ppc_find_refs.py code.bin <base_va_hex> <target_va_hex>
This is a triage helper, not a full control-flow or XEX parser.
"""
import struct
import sys


def sign_extend(value, bits):
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def main():
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} code.bin <base_va_hex> <target_va_hex>", file=sys.stderr)
        return 2

    path = sys.argv[1]
    base = int(sys.argv[2], 16)
    target = int(sys.argv[3], 16)
    data = open(path, "rb").read()
    if len(data) % 4:
        print("warning: trailing bytes ignored (code slice is not word-aligned)", file=sys.stderr)

    found = 0
    for off in range(0, len(data) - 3, 4):
        word = struct.unpack_from(">I", data, off)[0]
        pc = (base + off) & 0xFFFFFFFF
        opcode = word >> 26
        dest = None
        kind = None

        if opcode == 18:  # b / bl
            disp = sign_extend(word & 0x03FFFFFC, 26)
            dest = disp if word & 2 else (pc + disp) & 0xFFFFFFFF
            kind = "b"
        elif opcode == 16:  # bc / bcl
            disp = sign_extend(word & 0xFFFC, 16)
            dest = disp if word & 2 else (pc + disp) & 0xFFFFFFFF
            kind = "bc"

        if dest == target:
            link = " (link)" if word & 1 else ""
            print(f"{pc:08X}: {word:08X}  {kind} -> {dest:08X}{link}")
            found += 1

    print(f"Direct branch references: {found}")
    print("Note: indirect calls (bctr/bctrl), function pointers, and data references are not covered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
