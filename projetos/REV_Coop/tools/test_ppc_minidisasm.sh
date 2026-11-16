#!/usr/bin/env bash
set -euo pipefail
cc -std=c99 -Wall -Wextra -Werror -O2 \
  "$(dirname "$0")/ppc_minidisasm.c" -o /tmp/ppc_minidisasm

python3 - <<'PY'
import struct
words = [0x38600001, 0x90830020, 0x4E800020]
with open("/tmp/ppc-smoke.bin", "wb") as f:
    for word in words:
        f.write(struct.pack(">I", word))
PY

out=$(/tmp/ppc_minidisasm /tmp/ppc-smoke.bin 0 82001000 3)
printf '%s\n' "$out"
grep -q 'li r3,1' <<<"$out"
grep -q 'stw r4,32(r3)' <<<"$out"
grep -q 'bclr' <<<"$out"
echo "PowerPC disassembler smoke test: PASS"
