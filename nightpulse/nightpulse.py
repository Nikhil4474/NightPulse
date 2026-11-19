"""NightPulse on-board pipeline: raw ECG -> quality gate -> features -> risk score.
Usage: python3 nightpulse.py data/a01 [minutes]   (replays a PhysioNet recording as if live)"""
import sys, json, time, os
try:
    import resource
except ImportError:                      # Windows has no resource module
    import types as _t, time as _tm
    resource = _t.SimpleNamespace(RUSAGE_SELF=0, getrusage=lambda _w: _t.SimpleNamespace(ru_maxrss=0, ru_utime=_tm.process_time(), ru_stime=0.0))
import numpy as np, wfdb
from wfdb import processing
from scipy.signal import welch
from scipy.interpolate import interp1d
FS = 100
M = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'model.json')))
MEAN, SCALE, COEF = np.array(M['mean']), np.array(M['scale']), np.array(M['coef'])

def quality_ok(x, b):
    if np.ptp(x) < 1e-3 or np.std(x) < 1e-3: return False, 'flatline'
    if np.mean(np.abs(x) >= np.abs(x).max() * 0.999) > 0.02: return False, 'clipping'
    rr = np.diff(b)
    if len(b) < 30 or len(b) > 200: return False, 'beat count'
    if np.mean((rr > 0.3) & (rr < 2.0)) < 0.9: return False, 'irregular beats'
    return True, 'ok'

def minute_feats(b):
    rr = np.diff(b); rr = rr[(rr > 0.3) & (rr < 2.0)]; d = np.diff(rr)
    return [rr.mean(), rr.std(), np.sqrt(np.mean(d**2)), np.mean(np.abs(d) > 0.05), rr.std()/rr.mean(),
            rr.min(), rr.max(), np.percentile(rr, 90) - np.percentile(rr, 10), len(rr)]

def win_feats(b):
    rr = np.diff(b); tt = b[1:]; m = (rr > 0.3) & (rr < 2.0)
    if m.sum() < 100: return None
    rr = rr[m]; tt = tt[m]; t4 = np.arange(tt[0], tt[-1], 0.25)
    x = interp1d(tt, rr, fill_value='extrapolate')(t4)
    f, p = welch(x - x.mean(), fs=4, nperseg=min(len(x), 512))
    bd = lambda lo, hi: p[(f >= lo) & (f < hi)].sum(); tot = bd(0.0033, 0.4) + 1e-9
    return [bd(0.01, 0.04)/tot, bd(0.04, 0.15)/tot, bd(0.15, 0.4)/tot, np.log(bd(0.01, 0.04) + 1e-9)]

def detect(x):
    q = processing.XQRS(sig=x, fs=FS); q.detect(verbose=False); return q.qrs_inds

CLO, CHI = np.array(M['clip_lo']), np.array(M['clip_hi'])
OLO, OHI = np.array(M['ood_lo']), np.array(M['ood_hi'])

def ood(f):
    """True when the feature vector is far outside what the model was trained on (6+ of 29 features beyond the 0.5-99.5 percent range)."""
    f = np.array(f); return int(((f < OLO) | (f > OHI)).sum()) >= M['ood_max_features']

def score(f):
    z = (np.clip(np.array(f), CLO, CHI) - MEAN) / SCALE
    return float(1 / (1 + np.exp(-(z @ COEF + M['intercept']))))

def cpu_time(): r = resource.getrusage(resource.RUSAGE_SELF); return r.ru_utime + r.ru_stime

if __name__ == '__main__':
    rec = sys.argv[1]; nmin = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    r = wfdb.rdrecord(rec); sig = r.p_signal[:, 0]
    try: ann = wfdb.rdann(rec, 'apn').symbol
    except Exception: ann = None
    n = min(nmin, len(sig)//6000 - 3)
    # detect beats in 10-min chunks (as a live buffer would)
    t0 = time.perf_counter(); c0 = cpu_time()
    peaks = np.concatenate([detect(sig[s:s+60000]) + s for s in range(0, (n+3)*6000, 60000)])
    t = peaks / FS
    detect_ms = (time.perf_counter() - t0) * 1000
    lat = []; rows = []
    for m in range(2, n):
        ts = time.perf_counter()
        b = t[(t >= m*60) & (t < (m+1)*60)]; x = sig[m*6000:(m+1)*6000]
        ok, why = quality_ok(x, b)
        if not ok: rows.append((m, None, why)); lat.append((time.perf_counter()-ts)*1000); continue
        f0 = minute_feats(b); w = win_feats(t[(t >= (m-2)*60) & (t < (m+3)*60)])
        nb = []
        for k in (-1, 1, -2, 2):
            bb = t[(t >= (m+k)*60) & (t < (m+k+1)*60)]; xx = sig[(m+k)*6000:(m+k+1)*6000]
            nb += minute_feats(bb)[:4] if (len(xx) == 6000 and quality_ok(xx, bb)[0]) else [0.0]*4
        if w is None: rows.append((m, None, 'short window')); lat.append((time.perf_counter()-ts)*1000); continue
        if ood(f0 + w + nb): rows.append((m, None, 'outside trained range')); lat.append((time.perf_counter()-ts)*1000); continue
        s = score(f0 + w + nb); rows.append((m, s, 'ok')); lat.append((time.perf_counter()-ts)*1000)
    wall = time.perf_counter() - t0; cpu = cpu_time() - c0
    for m, s, why in rows[:12]:
        print(f'minute {m:3d}  ' + (f'risk {s:.2f}  {"APNEA-LIKE" if s>0.5 else "normal"}' if s is not None else f'UNKNOWN ({why})') + (f'   label {ann[m]}' if ann else ''))
    lat = np.array(lat); rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    print(f'\nminutes scored: {len(rows)}  abstained: {sum(1 for r in rows if r[1] is None)}')
    print(f'beat detection (XQRS) for {n+3} min of ECG: {detect_ms:.0f} ms total')
    print(f'per-minute scoring latency: mean {lat.mean():.2f} ms, p95 {np.percentile(lat,95):.2f} ms, max {lat.max():.2f} ms')
    print(f'total wall {wall:.2f} s, CPU {cpu:.2f} s ({100*cpu/wall:.0f}% of one core), peak memory {rss:.0f} MB')
    print(f'model size: {os.path.getsize("model.json")} bytes (29 weights)')
