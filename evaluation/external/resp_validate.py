import sys, glob, json, time, numpy as np, pandas as pd
sys.path.insert(0, 'nightpulse')
import resp as R
from scipy.signal import resample_poly, butter, sosfiltfilt, welch
def ref_rate(r):
    r = sosfiltfilt(butter(2, [0.08, 0.7], btype='band', fs=50, output='sos'), r - r.mean()); f, p = welch(r, fs=50, nperseg=len(r), nfft=1 << 15)
    m = (f >= 0.1) & (f <= 0.5); return 60 * f[m][np.argmax(p[m])]
rows = []; lat = []
for i in range(1, 54):
    s = pd.read_csv(f'work/bidmc/bidmc_{i:02d}_Signals.csv'); s.columns = [c.strip() for c in s.columns]
    nu = pd.read_csv(f'work/bidmc/bidmc_{i:02d}_Numerics.csv'); nu.columns = [c.strip() for c in nu.columns]
    ppg = resample_poly(s['PLETH'].values.astype(float), 2, 5); rsp = resample_poly(s['RESP'].values.astype(float), 2, 5)   # 125 Hz -> 50 Hz
    for a in range(0, len(ppg) - R.WIN * 50, 8 * 50):
        t0 = time.perf_counter(); r, info = R.breathing_rate(ppg[a:a + R.WIN * 50]); lat.append((time.perf_counter() - t0) * 1000)
        ref = ref_rate(rsp[a:a + R.WIN * 50]); num = nu["RESP"].values[a // 50:a // 50 + R.WIN]; num = np.nanmean(num) if np.isfinite(num).any() else np.nan
        rows.append(dict(rec=i, t=a / 50, est=r, ref=ref, num=num, agree=info.get('agree', False), **{('e_' + k): v for k, v in info.get('est', {}).items()}))
d = pd.DataFrame(rows); d.to_csv('resp_val.csv', index=False)
v = d.dropna(subset=['est']); e = (v.est - v.ref).abs()
te=v[v.rec%2==0];et=(te.est-te.ref).abs()
res = dict(held_out_even_records=dict(n=len(te),mae=round(et.mean(),2),within2=round((et<=2).mean(),3),baseline_mae_always_mean=round((te.ref-v[v.rec%2==1].ref.mean()).abs().mean(),2)),agree_flag_share=round(float(v.agree.mean()),3),windows=len(d), scored=len(v), abstained=round(1 - len(v) / len(d), 3), mae_vs_resp_waveform=round(e.mean(), 2), median_ae=round(e.median(), 2), within2=round((e <= 2).mean(), 3),
           mae_vs_monitor_numeric=round((v.est - v.num).abs().mean(), 2), baseline_mae_always_mean=round((v.ref - v.ref.mean()).abs().mean(), 2),
           agree_only=dict(n=int(v.agree.sum()), mae=round((v[v.agree].est - v[v.agree].ref).abs().mean(), 2)), disagree_only_mae=round((v[~v.agree].est - v[~v.agree].ref).abs().mean(), 2),
           per_method={k: round((v[k].dropna() - v.loc[v[k].notna(), 'ref']).abs().mean(), 2) for k in ('e_iv', 'e_av', 'e_fv') if k in v},
           latency_ms_mean=round(float(np.mean(lat)), 1), latency_ms_p95=round(float(np.percentile(lat, 95)), 1))
print(json.dumps(res, indent=1)); json.dump(res, open('resp_val.json', 'w'), indent=1)
