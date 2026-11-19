import sys, glob, os, numpy as np, wfdb
sys.path.insert(0, 'training')
import featlib as F
from scipy.signal import resample_poly
from multiprocessing import Pool
def one(p):
    r = os.path.basename(p)[:-4]; rec = wfdb.rdrecord(p[:-4]); x = resample_poly(rec.p_signal[:, 0], 5, 18)
    x = F.prep(x); t = F.beats(x); X, ok = F.feats(x, t); return r, X, ok
if __name__ == '__main__':
    with Pool(2) as pool: res = pool.map(one, sorted(glob.glob('mitdb/*.hea')))
    X = np.concatenate([r[1] for r in res]); ok = np.concatenate([r[2] for r in res]); g = np.concatenate([[r[0]] * len(r[1]) for r in res])
    np.savez('mitdb_feats.npz', X=X, ok=ok, g=g); print(len(X), 'minutes', ok.mean().round(3), 'usable')
