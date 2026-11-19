import numpy as np
from scipy.signal import welch, butter, sosfiltfilt, iirnotch, filtfilt, resample_poly
from scipy.interpolate import interp1d
from wfdb import processing
FS = 100
def qual(x, b):
    if np.ptp(x) < 1e-3 or np.std(x) < 1e-3: return False
    if np.mean(np.abs(x) >= np.abs(x).max() * 0.999) > 0.02: return False
    rr = np.diff(b)
    if len(b) < 30 or len(b) > 200: return False
    if np.mean((rr > 0.3) & (rr < 2.0)) < 0.9: return False
    return True
def minute_feats(b):
    rr = np.diff(b); m = (rr > 0.3) & (rr < 2.0); rr = rr[m]; d = np.diff(rr)
    return [rr.mean(), rr.std(), np.sqrt(np.mean(d**2)), np.mean(np.abs(d) > 0.05), rr.std()/rr.mean(), rr.min(), rr.max(), np.percentile(rr, 90) - np.percentile(rr, 10), len(rr)]
def win_feats(b):
    rr = np.diff(b); tt = b[1:]; m = (rr > 0.3) & (rr < 2.0)
    if m.sum() < 100: return None
    rr = rr[m]; tt = tt[m]; t4 = np.arange(tt[0], tt[-1], 0.25); x = interp1d(tt, rr, fill_value='extrapolate')(t4)
    f, p = welch(x - x.mean(), fs=4, nperseg=min(len(x), 512)); bd = lambda lo, hi: p[(f >= lo) & (f < hi)].sum(); tot = bd(0.0033, 0.4) + 1e-9
    return [bd(0.01, 0.04)/tot, bd(0.04, 0.15)/tot, bd(0.15, 0.4)/tot, np.log(bd(0.01, 0.04) + 1e-9)]
def prep(x100):
    """Same conditioning as the live EVM path: 60 Hz notch, 0.5-35 Hz band-pass, scale so the 99.5th percentile of |x| is 1."""
    b, a = iirnotch(60, 30, 100) if False else (None, None)
    y = sosfiltfilt(butter(3, [0.5, 35], btype='band', fs=100, output='sos'), x100 - np.mean(x100))
    return y / (np.percentile(np.abs(y), 99.5) + 1e-12)
def beats(x):
    out = []
    for s in range(0, len(x), 60000):
        seg = x[s:s + 60000]
        if len(seg) < 1500: continue
        try:
            q = processing.XQRS(sig=seg, fs=FS); q.detect(verbose=False); out.append(q.qrs_inds + s)
        except Exception: pass
    return np.concatenate(out) / FS if out else np.zeros(0)
def feats(sig, t):
    n = len(sig) // 6000; mq = []
    for m in range(n):
        b = t[(t >= m*60) & (t < (m+1)*60)]; xs = sig[m*6000:(m+1)*6000]
        mq.append(minute_feats(b) if qual(xs, b) else None)
    X = []; ok = []
    for m in range(n):
        f0 = mq[m]; w = win_feats(t[(t >= (m-2)*60) & (t < (m+3)*60)]) if f0 is not None else None; nb = []
        for k in (-1, 1, -2, 2):
            j = m + k; nb += (mq[j][:4] if 0 <= j < n and mq[j] is not None else [0.0]*4)
        if f0 is None or w is None: X.append([0.0]*29); ok.append(False)
        else: X.append(f0 + w + nb); ok.append(True)
    return np.array(X, float), np.array(ok)
