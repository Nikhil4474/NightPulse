import sys, glob, os, numpy as np
sys.path.insert(0, 'training')
import featlib as F
from multiprocessing import Pool
def one(p):
    s = os.path.basename(p)[:-4]; d = np.load(p); x = F.prep(d['ecg']); t = F.beats(x); X, ok = F.feats(x, t)
    lab = d['label'][:len(X) * 6000].reshape(-1, 6000) if len(d['label']) >= len(X) * 6000 else None
    state = np.array([np.bincount(l.astype(int), minlength=8).argmax() for l in lab]) if lab is not None else np.zeros(len(X), int)
    return s, X, ok, state, len(t)
if __name__ == '__main__':
    with Pool(2) as pool: res = pool.map(one, sorted(glob.glob('wesad_data/S*.npz')))
    X = np.concatenate([r[1] for r in res]); ok = np.concatenate([r[2] for r in res]); st = np.concatenate([r[3] for r in res]); g = np.concatenate([[r[0]] * len(r[1]) for r in res])
    np.savez('wesad_feats.npz', X=X, ok=ok, state=st, g=g); print(len(X), 'minutes', ok.mean().round(3), 'usable;', [(r[0], r[4]) for r in res][:3])
