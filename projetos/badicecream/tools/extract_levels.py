"""Extrai os XMLs de fase embutidos no ABC. Uso: extract_levels.py abc.bin pasta"""
import sys, re
d = open(sys.argv[1], 'rb').read()
levels = re.findall(rb'<level .*?</level>', d, re.S)
for i, x in enumerate(levels):
    open(f'{sys.argv[2]}/level{i:02d}.xml', 'wb').write(x)
print(len(levels), 'fases')
