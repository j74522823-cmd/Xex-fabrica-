"""Capcom's yz2 decompressor (the room archives St*/rNNN.das and etc/memcard.das), ported from
src/game/yz2code.cpp (set-up: header, models, dictionary) and the instructions of
src/game/yz2asm.cpp (yz2Decode_Decode, FrequencyDecode_Decode / _Decode768). The asm is the
reference; the label names below are its.

Stream (Yz2DecodeSet): a text header "<packed hex>\\t<unpacked hex>\\n", then the coded bytes at
the next 32-byte boundary after the second number (`(p + 0x20) & ~0x1F`). Decoding runs until
`unpacked` output bytes exist.

Range coder (FrequencyDecode_Decode, .L_801D4058..): state R (Yz2Dec.mask, primed 0x80) and C
(Yz2Dec.byte, primed with the first coded byte). Renormalise: R > 0x800000 nothing; R > 0x8000 one
byte (C = C << 8 | b, R <<= 8); R > 0x80 two bytes (<< 16); else three (<< 24). Then step = R >> 14,
value = C / step, symbol = the model's cumulative slot holding `value` (the asm fills a 0x8000-entry
lookup table `table[cum_start .. cum_start + cum_freq) = symbol` when the model changed, .L_801D4088;
a bisect on the same cumulative starts gives the same symbol), C -= step * cum_start,
R = (step * cum_freq) >> 1 (.L_801D40D0: `mullw r11, r11, r0; srwi r11, r11, 1`). The cumulative
table always totals 0x8000, so `value` < 0x8000.

Adaptive model (Yz2Freq): freq[n] u16, total (`max`), bits, range = 1 << bits, and the cumulative
table cum[i] = (scaled freq, scaled start) used by the coder. Reset (FREQ_RESET): freq[i] = 1,
total = n, bits = the smallest with n < 1 << bits (capped at 15), while cum keeps the set-up
distribution (MODEL_SETUP: 0x8000 counts dealt round-robin over the n symbols). After each symbol
(.L_801D40D0 tail): freq[s]++, total++, then
  - bits <= 14 and total == range (.L_801D415C): cum[i] = (freq[i] << (15 - bits), running sum),
    bits++, range = 1 << bits; the lookup table is marked stale;
  - bits == 15 and total > 0x7FFF (.L_801D41BC): cum[i] = (freq[i], running sum) from the
    unhalved counts, then freq[i] >>= 1 when > 1, total = the sum of the halved counts;
  - otherwise cum is not touched (the coder sees the model as of the last rebuild).

Main loop (yz2Decode_loop, yz2Decode_L01, yz2Decode_L02): s = main model (0x500 symbols).
  s >= 0x400 (`cmplwi r24, 0x3ff; ble`): literal byte s & 0xFF (`stb r24`), run length 1.
  s <  0x400: a dictionary run. ctx = the byte at the scan pointer (r21: the last output byte that
    has been entered into the dictionary = the byte before this run); ent = dic[ctx]
    (`slwi 10; add; slwi 2` = ctx * 0x1004); slot = (s + ent.cnt) & 0x1FF, ent.cnt being the next
    write slot of the 512-entry ring, so s & 0x1FF = 0x1FF is the newest entry, smaller is older.
    0x200 <= s <= 0x3FF (yz2Decode_L02): source = ent.ptr[slot], length = ent.len[slot].
    s <= 0x1FF (yz2Decode_L01 after `cmplwi r24, 0x1ff; bgt`): source = ent.ptr[slot], the length
    from the side model (0x100 symbols): t > 2: length = t - 1; t == 2: 16-bit, t == 1: 24-bit,
    t == 0: 32-bit big-endian value from further side symbols, minus 1 (`subi r24, r24, 1` at
    .L_801D3F28 on every path).
  The run is copied byte by byte (yz2Decode_str_trans_loop; it may overlap the output).
Dictionary entry (yz2Decode_dic_set): when the scan pointer r21 is before the last written byte,
  ctx = *r21, ent = dic[ctx]: ent.ptr[cnt] = r21 + 1, ent.len[cnt] = the length just written
  (1 for a literal), cnt = (cnt + 1) & 0x1FF, and r21 = the last written byte. So every literal
  and every copied run is entered under the byte that preceded it. Yz2DicEnt is {u32 cnt;
  u32 ptr[0x200]; u32 len[0x200]} (the C declares the halves as u8[0x800]).
"""
import re
from bisect import bisect_right

N_MAIN = 0x500
N_SIDE = 0x100
CUM_TOTAL = 0x8000
RING = 0x200

_HEADER = re.compile(rb'\s*([0-9A-Fa-f]+)(.)\s*([0-9A-Fa-f]+)')


class Yz2Error(ValueError):
    pass


def parse_header(data, base=0):
    """(packed, unpacked, stream offset) of the yz2 stream starting at data[base] (Yz2DecodeSet)."""
    m = _HEADER.match(data, base)
    if not m:
        raise Yz2Error('no yz2 header')
    packed = int(m.group(1), 16)
    unpacked = int(m.group(3), 16)
    start = (m.end(3) + 0x20) & ~0x1F
    return packed, unpacked, start


def is_yz2(data, base=0):
    """True when data[base] starts with a yz2 text header (hex, separator, hex); a raw container
    body starts with the u32 entry count, whose zero bytes match neither."""
    return bool(_HEADER.match(data, base, base + 32))


class _Model:
    """Yz2Freq + the coder's cumulative table."""
    __slots__ = ('n', 'freq', 'cum_f', 'cum_s', 'total', 'bits', 'range')

    def __init__(self, n):
        self.n = n
        # MODEL_SETUP: 0x8000 counts dealt round-robin, cum built from them
        f = [CUM_TOTAL // n + (1 if i < CUM_TOTAL % n else 0) for i in range(n)]
        self.cum_f = f[:]
        self.cum_s = []
        s = 0
        for x in f:
            self.cum_s.append(s)
            s += x
        # FREQ_RESET
        self.freq = [1] * n
        self.total = n
        bits = 0
        if n >= 1:
            while True:
                bits += 1
                if bits > 14:
                    break
                if n < (1 << bits):
                    break
        self.bits = bits
        self.range = 1 << bits


def decode(data, base=0):
    """Decompresses the yz2 stream at data[base]; returns (bytes, packed size, coded bytes read)."""
    packed, unpacked, pos = parse_header(data, base)
    out = bytearray(unpacked)
    main = _Model(N_MAIN)
    side = _Model(N_SIDE)
    # Yz2DecodeExec: mask = 0x80, byte = *src++
    R = 0x80
    C = data[pos]
    pos += 1
    # dictionary: 256 contexts x 512-entry rings of (ptr, len); the game zero-fills it (a reference
    # to a slot never written would copy from address 0), -1 here so that it fails instead
    dic_ptr = [-1] * (256 * RING)
    dic_len = [0] * (256 * RING)
    dic_cnt = [0] * 256

    def decode_sym(m):
        nonlocal R, C, pos
        # renormalise (.L_801D4000 / .L_801D402C)
        if R <= 0x800000:
            if R > 0x8000:
                C = ((C << 8) | data[pos]) & 0xFFFFFFFF
                R = (R << 8) & 0xFFFFFFFF
                pos += 1
            elif R > 0x80:
                C = ((C << 16) | (data[pos] << 8) | data[pos + 1]) & 0xFFFFFFFF
                R = (R << 16) & 0xFFFFFFFF
                pos += 2
            else:
                C = ((C << 24) | (data[pos] << 16) | (data[pos + 1] << 8) | data[pos + 2]) & 0xFFFFFFFF
                R = (R << 24) & 0xFFFFFFFF
                pos += 3
        step = R >> 14
        value = C // step
        if value >= CUM_TOTAL:
            raise Yz2Error(f'coder value {value:#x} outside the cumulative table at {pos:#x}')
        cum_s = m.cum_s
        s = bisect_right(cum_s, value) - 1
        # a slot of zero scaled frequency never holds `value`: freq >= 1 and the scale >= 1
        C = (C - step * cum_s[s]) & 0xFFFFFFFF
        R = (step * m.cum_f[s]) >> 1
        # model update
        freq = m.freq
        freq[s] += 1
        m.total += 1
        if m.bits <= 14:
            if m.total == m.range:
                sh = 15 - m.bits
                cf = m.cum_f
                cs = m.cum_s
                run = 0
                for i in range(m.n):
                    v = freq[i] << sh
                    cs[i] = run
                    run += v
                    cf[i] = v
                m.bits += 1
                m.range = 1 << m.bits
        elif m.total > 0x7FFF:
            cf = m.cum_f
            cs = m.cum_s
            run = 0
            total = 0
            for i in range(m.n):
                v = freq[i]
                cf[i] = v
                cs[i] = run
                run += v
                if v > 1:
                    v >>= 1
                    freq[i] = v
                total += v
            m.total = total
        return s

    o = 0          # r20: output position
    scan = 0       # r21: dictionary scan pointer
    end = unpacked
    while o < end:
        s = decode_sym(main)
        if s > 0x3FF:
            out[o] = s & 0xFF
            o += 1
            length = 1
        else:
            ctx = out[scan]
            ebase = ctx * RING
            slot = (s + dic_cnt[ctx]) & 0x1FF
            src = dic_ptr[ebase + slot]
            if s > 0x1FF:
                length = dic_len[ebase + slot]
            else:
                t = decode_sym(side)
                if t > 2:
                    length = t
                elif t == 2:
                    length = (decode_sym(side) << 8) | decode_sym(side)
                elif t == 1:
                    length = (decode_sym(side) << 16) | (decode_sym(side) << 8) | decode_sym(side)
                else:
                    length = (decode_sym(side) << 24) | (decode_sym(side) << 16) | (decode_sym(side) << 8) | decode_sym(side)
                length -= 1
            if length <= 0 or src < 0:
                raise Yz2Error(f'run of length {length} from dictionary slot {slot} of context {ctx:#x} '
                               f'({"never written" if src < 0 else "empty"}) at output {o:#x}')
            if o + length > end:
                raise Yz2Error(f'run of {length} bytes at output {o:#x} passes the end {end:#x}')
            if src + length <= o:
                out[o:o + length] = out[src:src + length]
            else:   # overlapping copy, byte by byte like yz2Decode_str_trans_loop
                for k in range(length):
                    out[o + k] = out[src + k]
            o += length
        # yz2Decode_dic_set
        last = o - 1
        if scan < last:
            ctx = out[scan]
            cnt = dic_cnt[ctx]
            dic_ptr[ctx * RING + cnt] = scan + 1
            dic_len[ctx * RING + cnt] = length
            dic_cnt[ctx] = (cnt + 1) & 0x1FF
            scan = last
    return bytes(out), packed, pos - parse_header(data, base)[2]


def main():
    """yz2.py <file.das | raw stream> [out]: decompress (a .das container's body starts at 0x400)
    and report the sizes; write the decompressed body to `out` when given."""
    import sys
    import time
    path = sys.argv[1]
    d = open(path, 'rb').read()
    base = 0 if is_yz2(d) else 0x400
    t = time.time()
    out, packed, used = decode(d, base)
    print(f'{path}: packed {packed:#x} (coder read {used:#x}), unpacked {len(out):#x}, {time.time() - t:.1f} s')
    if len(sys.argv) > 2:
        with open(sys.argv[2], 'wb') as f:
            f.write(out)


if __name__ == '__main__':
    main()
