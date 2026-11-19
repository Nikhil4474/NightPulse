"""Inert reader for OSASUD's pickle. No pandas or numpy code is executed: every pandas/functools global becomes a recording stub, numpy arrays are rebuilt by this file
from raw bytes, and float cell arrays are shrunk to float32 on the fly (the full file does not fit in 7 GB). Usage: python3 -I osasud_safe.py"""
import pickle, sys, numpy as np, resource, collections
resource.setrlimit(resource.RLIMIT_AS, (5_800_000_000, 5_800_000_000))
D = 'work/osasud/'
KEEP_LEN = 80
CNT = [0]
def junk(v):
    if isinstance(v, Arr): return True
    if isinstance(v, bytes): return len(v) > 2
    if isinstance(v, tuple):
        if len(v) == 1 and isinstance(v[0], int) and v[0] in (80, 20, 10, 5, 1): return True       # array shape
        if len(v) == 5 and v[0] == 1: return True                                                # array state
        if len(v) == 3 and v[0] is np.ndarray: return True                                       # _reconstruct args
    return False
class Arr:
    def __setstate__(self, st):
        CNT[0] += 1
        if CNT[0] % 500000 == 0: print(CNT[0], 'cells', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 'GB', flush=True)
        _, shape, dt, fortran, raw = st
        if dt.hasobject:
            a = np.empty(shape, dtype=object); a.reshape(-1)[:] = raw if not isinstance(raw, bytes) else None; self.a = a
        else:
            a = np.frombuffer(raw, dt).reshape(shape)
            self.a = a.astype(np.float32) if (a.ndim == 1 and a.size == KEEP_LEN and a.dtype.kind == 'f') else (None if (a.ndim == 1 and a.dtype.kind == 'f' and a.size < 40) else a.copy())
def _reconstruct(cls, shape, b): return Arr()
class Gen:
    def __init__(self, *a, **k): self.args, self.kw, self.state = a, k, None
    def __setstate__(self, st): self.state = st
    def __call__(self, *a, **k): g = Gen(*a, **k); g.func = self; return g
class U(pickle._Unpickler):          # pure-Python unpickler so memoization of per-cell bytes can be skipped
    dispatch = dict(pickle._Unpickler.dispatch)
    def load_memoize(self):
        i = getattr(self, 'nm', 0); self.nm = i + 1; v = self.stack[-1]
        if not junk(v): self.memo[i] = v
    dispatch[pickle.MEMOIZE[0]] = load_memoize
    def find_class(self, mod, name):
        if (mod, name) == ('numpy.core.multiarray', '_reconstruct'): return _reconstruct
        if (mod, name) == ('numpy', 'ndarray'): return np.ndarray
        if (mod, name) == ('numpy', 'dtype'): return np.dtype
        if mod.split('.')[0] in ('pandas', 'functools') or (mod, name) == ('builtins', 'object'): return Gen
        if mod == 'builtins' and name in ('slice', 'set', 'list', 'tuple', 'dict', 'range'): return getattr(__import__('builtins'), name)
        raise pickle.UnpicklingError(f'blocked {mod}.{name}')
if __name__ == '__main__':
    with open(D + 'dataset_OSAS.pickle', 'rb') as f: df = U(f).load()
    print(type(df), resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 'GB', flush=True)
    import pickle as pk; pk.dump(df, open(D + 'stub_tree.pkl', 'wb')) if False else None
    def show(x, d=0, key='', maxd=4):
        pad = '  ' * d
        if isinstance(x, Gen): print(pad + key, 'Gen', list(vars(x)), flush=True); [show(v, d + 1, k, maxd) for k, v in vars(x).items()] if d < maxd else None
        elif isinstance(x, Arr): print(pad + key, 'Arr', None if x.a is None else (x.a.shape, str(x.a.dtype)), flush=True)
        elif isinstance(x, (list, tuple)):
            print(pad + key, type(x).__name__, len(x), flush=True)
            if d < maxd: [show(a, d + 1, f'[{i}]', maxd) for i, a in enumerate(x[:6])]
        elif isinstance(x, dict):
            print(pad + key, 'dict', list(x)[:10], flush=True)
            if d < maxd: [show(v, d + 1, str(k), maxd) for k, v in list(x.items())[:6]]
        elif isinstance(x, np.ndarray): print(pad + key, 'ndarray', x.shape, x.dtype, x.reshape(-1)[:3], flush=True)
        else: print(pad + key, repr(x)[:100], flush=True)
    mg = df.state['_mgr']; blocks = mg.args[0]; axes = mg.args[1]
    def find_names(x, depth=0):
        if isinstance(x, Arr) and x.a is not None and x.a.dtype == object and x.a.size < 100: return list(x.a.reshape(-1))
        if depth > 5: return None
        kids = list(vars(x).values()) if isinstance(x, Gen) else (list(x.values()) if isinstance(x, dict) else (list(x) if isinstance(x, (list, tuple)) else []))
        for k in kids:
            r = find_names(k, depth + 1)
            if r: return r
        return None
    names = find_names(axes[0]); print('columns', names, flush=True)
    def plc(b): return [a for a in b.args if isinstance(a, (Arr, slice))][-1]
    col = {}
    for b in blocks:
        v = b.args[0]; pl = b.args[1]
        pos = list(pl.a) if isinstance(pl, Arr) else list(range(pl.start, pl.stop))
        if isinstance(v, Arr): col.update({names[p]: ('arr', v.a, k) for k, p in enumerate(pos)})
        else: print('non-array block at', pos, [names[p] for p in pos], flush=True)
    print({k: (type(v[1]).__name__, getattr(v[1], 'shape', None)) for k, v in col.items()}, flush=True)
    out = {}
    for k, (_, a, r) in col.items():
        row = a[r]
        if row.dtype == object:
            if hasattr(row[0], 'a'):
                n = 0 if row[0].a is None else row[0].a.size
                if k in ('signal_pleth', 'signal_ecg_ii') and n == 80:
                    arr = np.empty((len(row), 80), np.float32)
                    for q, c in enumerate(row): arr[q] = c.a
                    out['ppg' if k == 'signal_pleth' else 'ecg'] = arr; print(k, arr.shape, flush=True)
                a[r] = None                      # free the per-second cell arrays
            else: out[k] = np.array(row.astype(str))
        else: out[k] = row
    np.savez_compressed(D + 'osasud_small2.npz', **out); print('saved', {k: v.shape for k, v in out.items()}, flush=True)
