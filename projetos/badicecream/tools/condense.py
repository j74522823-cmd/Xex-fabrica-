import sys,re
src=open(sys.argv[1]).read().split('\n')
a,b=int(sys.argv[2]),int(sys.argv[3])
keep=re.compile(r'^\s*>?\s*(\d+)\s+(getlex|getproperty|setproperty|initproperty|callproperty|callpropvoid|callsuper|callsupervoid|constructprop|construct|pushbyte|pushshort|pushint|pushdouble|pushstring|pushnan|findpropstrict|if\w+|add|subtract|multiply|divide|modulo|negate|returnvalue|returnvoid|getslot|setslot|newarray|newobject|getsuper|increment|decrement|inclocal|inclocal_i|increment_i|decrement_i|lookupswitch|lessthan|equals|bitand|bitor|lshift|rshift|not|coerce\w*|astype\w*|getglobalscope|call|callmethod)\b(.*)$')
out=[]
for l in src[a-1:b]:
    s=l.strip()
    if s.startswith(('FIELD','METHOD','[','===')) or s.startswith('CONST') or s.startswith('CLASS'):
        out.append(l); continue
    m=keep.match(l)
    if m:
        op=m.group(2)
        if op in('coerce','coerce_a','coerce_s'): continue
        out.append('%5s %s%s'%(m.group(1),op,m.group(3)))
print('\n'.join(out))
