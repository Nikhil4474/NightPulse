"""Run the deployed ECG risk pipeline (NightPulse v4) on OSASUD lead II, per minute."""
import sys, os, pickle, numpy as np
P = os.path.abspath('work') + '/'   # run from the repo root
sys.path.insert(0, os.path.abspath('nightpulse')); os.chdir('nightpulse')
import nightpulse as NP
from scipy.signal import resample_poly
from multiprocessing import Pool
def run(args):
    p, x80 = args
    nanf = np.isnan(x80); x = np.where(nanf, 0.0, x80); sc = np.percentile(np.abs(x[~nanf]), 99.5) if (~nanf).any() else 1.0
    x = resample_poly(x / max(sc, 1e-9), 5, 4); nan100 = resample_poly(nanf.astype(float), 5, 4) > 0.01
    n = len(x) // 6000
    peaks = np.concatenate([NP.detect(x[s:s + 60000]) + s for s in range(0, n * 6000, 60000)]) if n > 5 else np.zeros(0); t = peaks / NP.FS
    rows = []
    for m in range(2, n - 3):
        if nan100[(m - 2) * 6000:(m + 3) * 6000].mean() > 0.05: rows.append((m, None, 'gap')); continue
        b = t[(t >= m * 60) & (t < (m + 1) * 60)]; xm = x[m * 6000:(m + 1) * 6000]; ok, why = NP.quality_ok(xm, b); s = None
        if ok:
            f0 = NP.minute_feats(b); w = NP.win_feats(t[(t >= (m - 2) * 60) & (t < (m + 3) * 60)]); nb = []
            for k in (-1, 1, -2, 2):
                bb = t[(t >= (m + k) * 60) & (t < (m + k + 1) * 60)]; xx = x[(m + k) * 6000:(m + k + 1) * 6000]
                nb += NP.minute_feats(bb)[:4] if (len(xx) == 6000 and NP.quality_ok(xx, bb)[0]) else [0.0] * 4
            if w is None: ok, why = False, 'short window'
            elif NP.ood(f0 + w + nb): ok, why = False, 'outside trained range'
            else: s = NP.score(f0 + w + nb)
        rows.append((m, s, why))
    print(p, n, 'min', sum(1 for r in rows if r[1] is not None), 'scored', flush=True); return p, rows
if __name__ == '__main__':
    d = np.load(P + 'osasud/osasud_small2.npz', allow_pickle=True); pat = d['patient']; ecg = d['ecg']
    jobs = [(p, ecg[pat == p].reshape(-1).astype(np.float64)) for p in sorted(set(pat.tolist()), key=int)]
    with Pool(2) as pool: res = dict(pool.imap_unordered(run, jobs))
    pickle.dump(res, open(P + 'osasud/ecg_scores.pkl', 'wb')); print('done')
