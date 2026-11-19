"""Cache per-patient PPG breathing features for OSASUD: breathing-band envelope (4 Hz grid), pulse gaps, beat times."""
import sys, numpy as np, pickle
sys.path.insert(0, 'nightpulse')
import resp as RS
from scipy.signal import resample_poly
D = 'work/osasud/'
d = np.load(D + 'osasud_small2.npz', allow_pickle=True); pat = d['patient']; ev = d['event']; ppg = d['ppg']
def segments(x, fs, min_len=120, bridge=1.0):
    ok = np.isfinite(x); idx = np.where(~ok)[0]
    if len(idx):                                   # bridge short NaN runs by interpolation
        z = np.diff(np.r_[0, (~ok).astype(int), 0]); st = np.where(z == 1)[0]; en = np.where(z == -1)[0]
        for a, b in zip(st, en):
            if (b - a) / fs <= bridge and a > 0 and b < len(x): x[a:b] = np.interp(np.arange(a, b), [a - 1, b], [x[a - 1], x[b]])
    ok = np.isfinite(x); z = np.diff(np.r_[0, ok.astype(int), 0]); st = np.where(z == 1)[0]; en = np.where(z == -1)[0]
    return [(a, b) for a, b in zip(st, en) if (b - a) / fs >= min_len]
out = {}
for p in sorted(set(pat.tolist()), key=int):
    m = pat == p; x = ppg[m].reshape(-1).astype(np.float64); N = m.sum()
    rec = dict(n_s=int(N), ev=ev[m], segs=[])
    for a, b in segments(x, 80):
        seg = resample_poly(x[a:b], 5, 8); r = RS.beats_and_series(seg)
        if r is None: continue
        t, ser, good = r; off = a / 80
        tg, w, env, base = RS.breath_wave(t, ser['iv'])
        gap = np.zeros(len(tg), bool)
        for u, v in zip(t[:-1], t[1:]):
            if v - u > 3: gap |= (tg >= u) & (tg <= v)
        rec['segs'].append(dict(off=off, tg=(tg + off).astype(np.float32), env=env.astype(np.float32), gap=gap, beats=(t + off).astype(np.float32), amp=ser['av'].astype(np.float32), iv=ser['iv'].astype(np.float32)))
    out[p] = rec; print(p, len(rec['segs']), 'segments', sum(len(s['tg']) for s in rec['segs']) / 4 / 3600, 'h of pulse', flush=True)
pickle.dump(out, open(D + 'ppg_feats.pkl', 'wb')); print('done')
