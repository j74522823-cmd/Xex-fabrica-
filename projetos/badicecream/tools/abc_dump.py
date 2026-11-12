"""Disassembler mínimo de ABC (AS3). Uso: python3 -I abc_dump.py abc.bin saida.txt"""
import sys, struct
d = open(sys.argv[1], 'rb').read()
# DoABC2: flags(4) + nome\0 + ABC
p = 4; p = d.index(b'\0', p) + 1
pos = p
def u30():
    global pos
    r = 0; s = 0
    while True:
        b = d[pos]; pos += 1
        r |= (b & 0x7f) << s; s += 7
        if not b & 0x80: break
    return r
def s32():
    r = u30()
    if r & 0x80000000: r -= 1 << 32
    return r
def u8():
    global pos; pos += 1; return d[pos-1]
minor, major = struct.unpack('<HH', d[pos:pos+4]); pos += 4
ints = [0]+[s32() for _ in range(max(0, u30()-1))]
n = u30(); uints = [0]+[u30() for _ in range(max(0, n-1))]
n = u30(); dbls = [0.0]
for _ in range(max(0, n-1)): dbls.append(struct.unpack('<d', d[pos:pos+8])[0]); pos += 8
n = u30(); strs = ['']
for _ in range(max(0, n-1)):
    l = u30(); strs.append(d[pos:pos+l].decode('utf8', 'replace')); pos += l
n = u30(); nss = [('', '')]
for _ in range(max(0, n-1)):
    k = u8(); nm = u30(); nss.append((k, strs[nm]))
n = u30(); nssets = [[]]
for _ in range(max(0, n-1)):
    c = u30(); nssets.append([u30() for _ in range(c)])
n = u30(); mns = [None]
for _ in range(max(0, n-1)):
    k = u8()
    if k in (7, 0xd): ns = u30(); nm = u30(); mns.append(('Q', nss[ns][1], strs[nm]))
    elif k in (0xf, 0x10): nm = u30(); mns.append(('RT', '', strs[nm]))
    elif k in (0x11, 0x12): mns.append(('RTL', '', '*'))
    elif k in (9, 0xe): nm = u30(); u30(); mns.append(('M', '', strs[nm]))
    elif k in (0x1b, 0x1c): u30(); mns.append(('ML', '', '*'))
    elif k == 0x1d:
        b = u30(); c = u30(); [u30() for _ in range(c)]; mns.append(('G', '', 'G'+str(b)))
    else: raise Exception('mn kind %x' % k)
def mname(i):
    if i == 0: return '*'
    if i >= len(mns): return '?%d' % i
    m = mns[i]
    if not m: return '?'
    if m[0] == 'G': return mname_g(i)
    return (m[1]+'.' if m[1] else '') + m[2]
def mname_g(i): return 'Vector'
n = u30(); methods = []
for _ in range(n):
    pc = u30(); rt = u30(); pt = [u30() for _ in range(pc)]; nm = u30(); fl = u8()
    if fl & 8:
        for _ in range(u30()): u30(); u8()
    if fl & 0x80:
        for _ in range(pc): u30()
    methods.append(dict(name=strs[nm], params=[mname(x) for x in pt], ret=mname(rt), body=None))
n = u30()
for _ in range(n):
    u30()
    for _ in range(u30()): u30(); u30()
def traits():
    out = []
    for _ in range(u30()):
        nm = u30(); kd = u8(); k = kd & 15; at = kd >> 4; t = dict(name=mname(nm), kind=k)
        if k in (0, 6):
            t['slot'] = u30(); t['type'] = mname(u30()); vi = u30()
            if vi:
                vk = u8()
                t['val'] = {3: lambda: ints[vi], 4: lambda: uints[vi], 6: lambda: dbls[vi], 1: lambda: strs[vi]}.get(vk, lambda: '?%d' % vk)()
        elif k == 4: u30(); u30()
        elif k in (1, 2, 3, 5): u30(); t['m'] = u30()
        if at & 4:
            for _ in range(u30()): u30()
        out.append(t)
    return out
def read_cls_info():
    pass
ni = u30(); insts = []
for _ in range(ni):
    nm = u30(); sp = u30(); fl = u8()
    if fl & 8: u30()
    itf = [mname(u30()) for _ in range(u30())]
    init = u30(); tr = traits()
    insts.append(dict(name=mname(nm), super=mname(sp), init=init, traits=tr, itf=itf))
for i in range(ni):
    ci = u30(); insts[i]['cinit'] = ci; insts[i]['ctraits'] = traits()
ns = u30()
for _ in range(ns): u30(); traits()
nb = u30()
OPS = {0x01:'bkpt',0x02:'nop',0x03:'throw',0x04:'getsuper',0x05:'setsuper',0x06:'dxns',0x07:'dxnslate',0x08:'kill',0x09:'label',0x0c:'ifnlt',0x0d:'ifnle',0x0e:'ifngt',0x0f:'ifnge',0x10:'jump',0x11:'iftrue',0x12:'iffalse',0x13:'ifeq',0x14:'ifne',0x15:'iflt',0x16:'ifle',0x17:'ifgt',0x18:'ifge',0x19:'ifstricteq',0x1a:'ifstrictne',0x1b:'lookupswitch',0x1c:'pushwith',0x1d:'popscope',0x1e:'nextname',0x1f:'hasnext',0x20:'pushnull',0x21:'pushundefined',0x23:'nextvalue',0x24:'pushbyte',0x25:'pushshort',0x26:'pushtrue',0x27:'pushfalse',0x28:'pushnan',0x29:'pop',0x2a:'dup',0x2b:'swap',0x2c:'pushstring',0x2d:'pushint',0x2e:'pushuint',0x2f:'pushdouble',0x30:'pushscope',0x31:'pushnamespace',0x32:'hasnext2',0x40:'newfunction',0x41:'call',0x42:'construct',0x43:'callmethod',0x44:'callstatic',0x45:'callsuper',0x46:'callproperty',0x47:'returnvoid',0x48:'returnvalue',0x49:'constructsuper',0x4a:'constructprop',0x4c:'callproplex',0x4e:'callsupervoid',0x4f:'callpropvoid',0x55:'newobject',0x56:'newarray',0x57:'newactivation',0x58:'newclass',0x59:'getdescendants',0x5a:'newcatch',0x5d:'findpropstrict',0x5e:'findproperty',0x60:'getlex',0x61:'setproperty',0x62:'getlocal',0x63:'setlocal',0x64:'getglobalscope',0x65:'getscopeobject',0x66:'getproperty',0x68:'initproperty',0x6a:'deleteproperty',0x6c:'getslot',0x6d:'setslot',0x70:'convert_s',0x71:'esc_xelem',0x72:'esc_xattr',0x73:'convert_i',0x74:'convert_u',0x75:'convert_d',0x76:'convert_b',0x77:'convert_o',0x78:'checkfilter',0x80:'coerce',0x82:'coerce_a',0x85:'coerce_s',0x86:'astype',0x87:'astypelate',0x90:'negate',0x91:'increment',0x92:'inclocal',0x93:'decrement',0x94:'declocal',0x95:'typeof',0x96:'not',0x97:'bitnot',0xa0:'add',0xa1:'subtract',0xa2:'multiply',0xa3:'divide',0xa4:'modulo',0xa5:'lshift',0xa6:'rshift',0xa7:'urshift',0xa8:'bitand',0xa9:'bitor',0xaa:'bitxor',0xab:'equals',0xac:'strictequals',0xad:'lessthan',0xae:'lessequals',0xaf:'greaterthan',0xb0:'greaterequals',0xb1:'instanceof',0xb2:'istype',0xb3:'istypelate',0xb4:'in',0xc0:'increment_i',0xc1:'decrement_i',0xc2:'inclocal_i',0xc3:'declocal_i',0xc4:'negate_i',0xc5:'add_i',0xc6:'subtract_i',0xc7:'multiply_i',0xd0:'getlocal0',0xd1:'getlocal1',0xd2:'getlocal2',0xd3:'getlocal3',0xd4:'setlocal0',0xd5:'setlocal1',0xd6:'setlocal2',0xd7:'setlocal3',0xef:'debug',0xf0:'debugline',0xf1:'debugfile',0x35:'li8',0x36:'li16',0x37:'li32'}
import io
def disasm(code):
    """Percorre só o código alcançável a partir do offset 0 (a ofuscação põe lixo depois de saltos)."""
    global d, pos
    sd, sp = d, pos
    d = code
    seen = {}; work = [0]
    BR = (0x0c,0x0d,0x0e,0x0f,0x10,0x11,0x12,0x13,0x14,0x15,0x16,0x17,0x18,0x19,0x1a)
    while work:
        a = work.pop()
        while a < len(d) and a not in seen:
            pos = a; o = u8(); nm = OPS.get(o, 'op%02x' % o); arg = ''; nxt = []; stop = False
            if o in BR:
                off = d[pos]|(d[pos+1]<<8)|(d[pos+2]<<16); pos += 3
                if off & 0x800000: off -= 1<<24
                arg = 'L%d' % (pos+off); nxt.append(pos+off)
                if o == 0x10: stop = True
            elif o == 0x1b:
                base = a
                dflt = d[pos]|(d[pos+1]<<8)|(d[pos+2]<<16); pos += 3
                if dflt & 0x800000: dflt -= 1<<24
                c = u30(); offs = [base+dflt]
                for _ in range(c+1):
                    v = d[pos]|(d[pos+1]<<8)|(d[pos+2]<<16); pos += 3
                    if v & 0x800000: v -= 1<<24
                    offs.append(base+v)
                nxt += offs; arg = ' '.join('L%d' % x for x in offs); stop = True
            elif o == 0x24: v = d[pos]; pos += 1; arg = str(v-256 if v > 127 else v)
            elif o == 0x25: arg = str(s32())
            elif o == 0x2c: arg = repr(strs[u30()])
            elif o == 0x2d: arg = str(ints[u30()])
            elif o == 0x2e: arg = str(uints[u30()])
            elif o == 0x2f: arg = str(dbls[u30()])
            elif o in (0x5d,0x5e,0x60,0x61,0x66,0x68,0x6a,0x80,0x86,0xb2,0x59,0x04,0x05): arg = mname(u30())
            elif o in (0x58,0x5a,0x40,0x31): arg = str(u30())
            elif o in (0x46,0x4c,0x4f,0x4a,0x45,0x4e): m = mname(u30()); c = u30(); arg = '%s argc=%d' % (m, c)
            elif o in (0x43,0x44): arg = '%d argc=%d' % (u30(), u30())
            elif o in (0x41,0x42,0x49,0x55,0x56,0x62,0x63,0x6c,0x6d,0x65,0x08,0x92,0x94): arg = str(u30())
            elif o == 0x32: arg = '%d %d' % (u30(), u30())
            elif o == 0xef: u8(); u30(); u8(); u30()
            elif o == 0xf0: arg = str(u30())
            elif o == 0xf1: arg = strs[u30()]
            if o in (0x03,0x47,0x48): stop = True
            seen[a] = (nm, arg)
            work += nxt
            if stop: break
            a = pos
    d, pos = sd, sp
    targets = set()
    for nm, arg in seen.values():
        for t in arg.split():
            if t.startswith('L') and t[1:].isdigit(): targets.add(int(t[1:]))
    lines = []
    for a in sorted(seen):
        nm, arg = seen[a]
        if nm in ('debugline', 'debugfile', 'debug', 'label'): continue
        lines.append('%s%5d %s %s' % ('>' if a in targets else ' ', a, nm, arg))
    return lines
for _ in range(nb):
    mi = u30(); ms = u30(); lc = u30(); isd = u30(); msd = u30(); cl = u30()
    code = d[pos:pos+cl]; pos += cl
    for _ in range(u30()): u30(); u30(); u30(); u30(); u30()
    traits()
    methods[mi]['body'] = code
out = open(sys.argv[2], 'w')
def dump_m(mi, ind=''):
    m = methods[mi]
    out.write('%s  METHOD %s(%s):%s\n' % (ind, m['name'], ', '.join(m['params']), m['ret']))
    if m['body']:
        for l in disasm(m['body']): out.write('%s    %s\n' % (ind, l))
for ins in insts:
    out.write('\n=== CLASS %s extends %s\n' % (ins['name'], ins['super']))
    for t in ins['traits']:
        if t['kind'] in (0, 6): out.write('  FIELD %s : %s%s\n' % (t['name'], t.get('type'), (' = %r' % (t['val'],)) if 'val' in t else ''))
    out.write('  [ctor]\n'); dump_m(ins['init'])
    for t in ins['traits']:
        if t['kind'] in (1, 2, 3, 5): out.write('  [%s]\n' % t['name']); dump_m(t['m'])
    out.write('  [static init]\n'); dump_m(ins['cinit'])
    for t in ins['ctraits']:
        if t['kind'] in (0, 6): out.write('  STATIC %s : %s%s\n' % (t['name'], t.get('type'), (' = %r' % (t['val'],)) if 'val' in t else ''))
        if t['kind'] in (1, 2, 3, 5): out.write('  [static %s]\n' % t['name']); dump_m(t['m'])
print(len(insts), 'classes,', len(methods), 'métodos')
