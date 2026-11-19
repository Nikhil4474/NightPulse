# Extract chest ECG (700 Hz) + label from WESAD with a restricted unpickler (no arbitrary code), resample to 100 Hz, save npz.
import sys, zipfile, pickle, io, numpy as np, os
from scipy.signal import decimate
ZIP, OUT = sys.argv[1], sys.argv[2]
ALLOWED = {('numpy', '_reconstruct'), ('numpy', 'ndarray'), ('numpy', 'dtype'), ('numpy', 'scalar'), ('collections', 'OrderedDict'), ('builtins', 'dict'), ('builtins', 'list'), ('builtins', 'tuple'), ('builtins', 'set'), ('builtins', 'bytearray'), ('_codecs', 'encode')}
class U(pickle.Unpickler):
    def find_class(self, mod, name):
        root = mod.split('.')[0]
        if (root, name) in ALLOWED or (root == 'numpy' and name in ('_reconstruct', 'ndarray', 'dtype', 'scalar')): return super().find_class(mod, name)
        raise pickle.UnpicklingError(f'blocked {mod}.{name}')
z = zipfile.ZipFile(ZIP)
for n in sorted(x for x in z.namelist() if x.endswith('.pkl')):
    s = os.path.basename(n)[:-4]
    if os.path.exists(f'{OUT}/{s}.npz'): continue
    with z.open(n) as f: d = U(io.BytesIO(f.read()), encoding='latin1').load()
    ecg = np.asarray(d['signal']['chest']['ECG'], float).ravel(); lab = np.asarray(d['label']).ravel()
    e100 = decimate(ecg, 7, ftype='fir', zero_phase=True); l100 = lab[::7][:len(e100)]
    np.savez_compressed(f'{OUT}/{s}.npz', ecg=e100, label=l100); print(s, len(ecg)/700/60, 'min', np.unique(lab), flush=True)
