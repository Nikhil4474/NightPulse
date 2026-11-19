"""Load OSASUD safely (restricted unpickler: only numpy/pandas/datetime classes, no loaders or shell-ish callables) and keep per-patient PPG (80 Hz), airflow and labels."""
import pickle, io, sys, numpy as np, resource
D = 'work/osasud/'
BAD = ('load', 'eval', 'exec', 'system', 'popen', 'compile', 'fromfile', 'memmap', 'read_', 'to_', 'open', 'save', 'testing', 'f2py', 'ctypeslib', 'distutils', 'lib.npyio', 'subprocess', 'os', 'sys')
class U(pickle.Unpickler):
    def find_class(self, mod, name):
        ok = mod.split('.')[0] in ('numpy', 'pandas', 'datetime', 'dateutil', 'pytz', 'zoneinfo') or (mod == 'builtins' and name in ('set', 'frozenset', 'list', 'dict', 'tuple', 'slice', 'range', 'object', 'bytearray', 'complex', 'int', 'float', 'str', 'bytes')) or (mod == 'collections' and name == 'OrderedDict') or (mod == 'functools' and name == 'partial') or (mod == '_codecs' and name == 'encode')
        if not ok or any(b in (mod + '.' + name).lower().replace('_', '', 0) for b in ('.load', '.eval', '.exec', 'system', 'popen', 'fromfile', 'memmap', 'read_pickle', 'read_', '.save', 'testing', 'f2py', 'subprocess')): raise pickle.UnpicklingError(f'blocked {mod}.{name}')
        return super().find_class(mod, name)
with open(D + 'dataset_OSAS.pickle', 'rb') as f: ds = U(f).load()
print(type(ds), ds.shape, list(ds.columns), 'maxrss GB', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, flush=True)
out = {}
for pat in ds['patient'].unique():
    t = ds[ds['patient'] == pat]
    out[f'p{pat}_ppg'] = np.concatenate(t['signal_pleth'].values).astype(np.float32)
    out[f'p{pat}_ann'] = t['annotation'].values.astype(str)
    for c in ('PSG_nasal_airflow', 'PSG_thoracic', 'PSG_abdominal'):
        if c in ds.columns: out[f'p{pat}_{c}'] = np.concatenate(t[c].values).astype(np.float32)
    if 'SpO2(%)' in ds.columns: out[f'p{pat}_spo2'] = t['SpO2(%)'].values.astype(np.float32)
    print(pat, len(t), 's', np.unique(out[f'p{pat}_ann'], return_counts=True), flush=True)
np.savez_compressed(D + 'osasud_small.npz', **out); print('saved')
