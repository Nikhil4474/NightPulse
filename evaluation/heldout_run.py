"""Held-out evaluation: run the DEPLOYED pipeline (nightpulse/nightpulse.py) on the PhysioNet Apnea-ECG test records x01-x35.
Usage (from the repo root):  python3 evaluation/heldout_run.py <dir with x01..x35 .dat/.hea/.apn> <output dir for per-record pickles>
Each pickle holds rows (minute, score or None, reason, apnea_label). Then run evaluation/heldout_metrics.py <output dir>."""
import sys, os, time, pickle, numpy as np, wfdb
D = os.path.abspath(sys.argv[1]) + '/'
O = os.path.abspath(sys.argv[2]) + '/'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'nightpulse')); os.chdir(os.path.join(ROOT, 'nightpulse'))
import nightpulse as NP
from multiprocessing import Pool
os.makedirs(O, exist_ok=True)
def run(rec):
    fn = O + rec + '.pkl'
    if os.path.exists(fn): return rec
    t0 = time.time(); r = wfdb.rdrecord(D + rec); sig = r.p_signal[:, 0]; ann = wfdb.rdann(D + rec, 'apn').symbol
    n = min(len(ann), len(sig) // 6000)
    peaks = np.concatenate([NP.detect(sig[s:s + 60000]) + s for s in range(0, n * 6000, 60000)]); t = peaks / NP.FS
    rows = []
    for m in range(2, n - 3):
        b = t[(t >= m * 60) & (t < (m + 1) * 60)]; x = sig[m * 6000:(m + 1) * 6000]; ok, why = NP.quality_ok(x, b); sc = None
        if ok:
            f0 = NP.minute_feats(b); w = NP.win_feats(t[(t >= (m - 2) * 60) & (t < (m + 3) * 60)]); nb = []
            for k in (-1, 1, -2, 2):
                bb = t[(t >= (m + k) * 60) & (t < (m + k + 1) * 60)]; xx = sig[(m + k) * 6000:(m + k + 1) * 6000]
                nb += NP.minute_feats(bb)[:4] if (len(xx) == 6000 and NP.quality_ok(xx, bb)[0]) else [0.0] * 4
            if w is None: ok, why = False, 'short window'
            elif NP.ood(f0 + w + nb): ok, why = False, 'outside trained range'
            else: sc = NP.score(f0 + w + nb)
        rows.append((m, sc, why, ann[m] == 'A'))
    pickle.dump(rows, open(fn, 'wb')); print(rec, n, 'min', round(time.time() - t0), 's', flush=True); return rec
if __name__ == '__main__':
    recs = sorted(f[:-4] for f in os.listdir(D) if f.endswith('.apn'))
    with Pool(2) as p: list(p.imap_unordered(run, recs))
    print('ALLDONE', flush=True)
