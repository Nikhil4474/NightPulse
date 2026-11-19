import sys, time, numpy as np, pandas as pd, pickle
sys.path.insert(0, 'nightpulse')
import resp as R; R.RAW = True
from scipy.signal import resample_poly, butter, sosfiltfilt, welch
from multiprocessing import Pool
B='work/bidmc/'
def ref_rate(r):
    r = sosfiltfilt(butter(2, [0.08, 0.7], btype='band', fs=50, output='sos'), r - r.mean()); f, p = welch(r, fs=50, nperseg=len(r), nfft=1 << 15)
    m = (f >= 0.1) & (f <= 0.5); return 60 * f[m][np.argmax(p[m])]
def one(i):
    s = pd.read_csv(f'{B}bidmc_{i:02d}_Signals.csv'); s.columns = [c.strip() for c in s.columns]
    ppg = resample_poly(s['PLETH'].values.astype(float), 2, 5); rsp = resample_poly(s['RESP'].values.astype(float), 2, 5); out = []
    for W in (32, 64):
        for a in range(0, len(ppg) - W * 50, 8 * 50):
            _, info = R.breathing_rate(ppg[a:a + W * 50])
            out.append(dict(rec=i, W=W, t=a / 50, ref=ref_rate(rsp[a:a + W * 50]), raw=info.get('raw'), good=info.get('good', 0), nb=info.get('nb', 0)))
    return out
if __name__ == '__main__':
    with Pool(2) as p: res = p.map(one, range(1, 54))
    pickle.dump([r for x in res for r in x], open('resp_cache.pkl', 'wb')); print('ok', sum(len(x) for x in res))
