#!/usr/bin/env bash
set -euo pipefail
tools_dir="$(dirname "$0")"
cc -std=c99 -Wall -Wextra -Werror -O2 \
  "$tools_dir/ppc_minidisasm.c" -o /tmp/ppc_minidisasm

python3 - <<'PY'
import struct
words = [0x38600001, 0x90830020, 0x4E800020]
with open("/tmp/ppc-smoke.bin", "wb") as f:
    for word in words:
        f.write(struct.pack(">I", word))
# A relative branch from 0x82001000 to 0x82001020.
with open("/tmp/ppc-refs.bin", "wb") as f:
    f.write(struct.pack(">II", 0x48000020, 0x60000000))
PY

out=$(/tmp/ppc_minidisasm /tmp/ppc-smoke.bin 0 82001000 3)
printf '%s\n' "$out"
grep -q 'li r3,1' <<<"$out"
grep -q 'stw r4,32(r3)' <<<"$out"
grep -q 'bclr' <<<"$out"

refs=$(python3 "$tools_dir/ppc_find_refs.py" /tmp/ppc-refs.bin 82001000 82001020)
printf '%s\n' "$refs"
grep -q '82001000: 48000020  b -> 82001020' <<<"$refs"
grep -q 'Direct branch references: 1' <<<"$refs"
echo "PowerPC disassembler and reference scanner tests: PASS"
