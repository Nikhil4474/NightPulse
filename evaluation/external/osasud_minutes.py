import pickle, sys, os, numpy as np, pandas as pd
P = os.path.abspath('work') + '/'   # run from the repo root
sys.path.insert(0, os.path.abspath('nightpulse')); os.chdir('nightpulse')
import nightpulse as NP
F = pickle.load(open(P + 'osasud/ppg_feats.pkl', 'rb')); E = pickle.load(open(P + 'osasud/ecg_scores.pkl', 'rb'))
def cyc(t, v, lo=0.01, hi=0.04):
    """fraction of 0.0033-0.4 Hz power in the 0.01-0.04 Hz band for a per-beat series (cyclic variation typical of repeated apnea)."""
    from scipy.signal import welch
    if len(t) < 100: return np.nan
    tg = np.arange(t[0], t[-1], 0.25); 
    if len(tg) < 400: return np.nan
    x = np.interp(tg, t, v); f, p = welch(x - x.mean(), fs=4, nperseg=min(len(x), 512)); bd = lambda a, b: p[(f >= a) & (f < b)].sum()
    return bd(lo, hi) / (bd(0.0033, 0.4) + 1e-12)
rows = []
for p, r in F.items():
    ev = r['ev']; N = r['n_s'] // 60
    if not r['segs']: continue
    tg = np.concatenate([s['tg'] for s in r['segs']]); env = np.concatenate([s['env'] for s in r['segs']]); gap = np.concatenate([s['gap'] for s in r['segs']])
    bt = np.concatenate([s['beats'] for s in r['segs']]); amp = np.concatenate([s['amp'] for s in r['segs']]); iv = np.concatenate([s['iv'] for s in r['segs']])
    ser = pd.Series(env); ratio = env / ser.rolling(1200, min_periods=240).quantile(0.75).shift(1).values      # vs 5 min q75, causal
    ratio_s = pd.Series(ratio).rolling(32, min_periods=16).mean().values                                         # 8 s smoothing
    ampn = amp / pd.Series(amp).rolling(600, min_periods=100).median().shift(1).values                          # vs about 10 min median
    ecg = {m: s for m, s, why in E.get(p, [])}
    for m in range(2, N - 3):
        a, b = np.searchsorted(tg, [60 * m, 60 * m + 60]); i0, i1 = np.searchsorted(bt, [60 * m, 60 * m + 60])
        nb = i1 - i0; y = int((ev[60 * m:60 * m + 60] != 'NONE').sum() >= 5); ya = int(np.array([s.startswith('APNEA') for s in ev[60 * m:60 * m + 60]]).sum() >= 5)
        row = dict(p=p, m=m, y=y, ya=ya, ecg=ecg.get(m), nb=nb)
        if b - a < 200 or nb < 30 or gap[a:b].mean() > 0.2: rows.append(row); continue
        rr = np.diff(bt[i0:i1]); v = (rr > 0.3) & (rr < 2.0)
        if v.mean() < 0.8: rows.append(row); continue
        r_ = ratio[a:b]; rs = ratio_s[a:b]; ok = np.isfinite(r_)
        row.update(ok=1, r_mean=np.nanmean(r_), r_lt50=np.nanmean(r_[ok] < 0.5) if ok.any() else np.nan, r_lt35=np.nanmean(r_[ok] < 0.35) if ok.any() else np.nan, r_min=np.nanmin(rs) if np.isfinite(rs).any() else np.nan, r_std=np.nanstd(r_),
                   a_mean=np.nanmean(ampn[i0:i1]), a_cv=np.std(amp[i0:i1]) / (np.mean(amp[i0:i1]) + 1e-9), a_min=np.nanmin(ampn[i0:i1]) if np.isfinite(ampn[i0:i1]).any() else np.nan)
        mf = NP.minute_feats(bt[i0:i1].astype(float)); row.update(rr_mean=mf[0], rr_sd=mf[1], rr_rmssd=mf[2], rr_pnn=mf[3], rr_cv=mf[4], rr_rng=mf[7])
        j0, j1 = np.searchsorted(bt, [60 * (m - 2), 60 * (m + 3)]); w = NP.win_feats(bt[j0:j1].astype(float))
        if w is not None: row.update(w_vlf=w[0], w_lf=w[1], w_hf=w[2], w_lvl=w[3])
        row.update(c_amp=cyc(bt[j0:j1], amp[j0:j1]), c_iv=cyc(bt[j0:j1], iv[j0:j1]))
        rows.append(row)
    print(p, flush=True)
df = pd.DataFrame(rows); df.to_pickle(P + 'osasud/minutes.pkl'); print(df.shape, df.ok.sum() if 'ok' in df else 0)
