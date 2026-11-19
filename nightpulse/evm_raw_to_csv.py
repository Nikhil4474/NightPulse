"""Recover a recording from the autosaved raw capture (data/live_*.raw), e.g. after Ctrl+C or a crash.
Usage: python3 evm_raw_to_csv.py data/live_20261103_220000.raw   -> writes the TI-style CSV and a 100 Hz recording next to it."""
import sys, os, numpy as np
from evm_live import Decoder, save, V
p = sys.argv[1]; name = os.path.basename(p)[:-4]
d = Decoder(); d.feed(open(p, 'rb').read()); s = d.split()
if s is None: sys.exit('not enough data in the file')
ecg_v, tia_v, ecg_r, tia_r = s; print(len(d.words), 'words, frame offset', d.offset)
out = save(name, ecg_v, tia_v, ecg_r, tia_r); print('saved', out); os.system(f'{sys.executable} afe_csv.py {out} {name}')
