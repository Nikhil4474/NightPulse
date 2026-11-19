"""PPG breathing branch for NightPulse. Input: optical (PPG) samples at 50 Hz. Output: breathing rate (breaths/min) and pause candidates.
Three respiratory modulations are taken from each pulse (intensity, amplitude, interval), resampled to 4 Hz, and the spectral peak in 0.1-0.5 Hz
(6-30 breaths/min) is found for each; they are fused by agreement. Window 32 s. Research prototype, not a medical measurement."""
import numpy as np
from scipy.signal import butter, sosfiltfilt, find_peaks, welch
FS = 50; WIN = 32; BAND = (0.1, 0.5)
_SOS_BEAT = butter(3, [0.5, 6.0], btype='band', fs=FS, output='sos'); _SOS_WIDE = butter(2, [0.08, 8.0], btype='band', fs=FS, output='sos')

def _spec_peak(t, v, t_end):
    """4 Hz resample of a per-beat series, detrend, return (rate_br_min, peak_power_fraction)."""
    if len(t) < 8: return None, 0.0
    tg = np.arange(t[0], t[-1], 0.25)
    if len(tg) < 4 * 12: return None, 0.0
    x = np.interp(tg, t, v); x = x - np.polyval(np.polyfit(tg, x, 1), tg)
    f, p = welch(x, fs=4, nperseg=len(x), nfft=2048)
    m = (f >= BAND[0]) & (f <= BAND[1]); tot = p[(f >= 0.05) & (f <= 1.0)].sum() + 1e-12
    k = np.argmax(p[m]); return 60 * f[m][k], float(p[m][k] * (f[1] - f[0]) * 6 / tot) if False else float(p[m][k] / tot)

def beats_and_series(x):
    """Pulse detection and the three modulation series. x: raw PPG at 50 Hz. Returns beat times and dict of series, or None."""
    xb = sosfiltfilt(_SOS_BEAT, x - np.mean(x)); xw = sosfiltfilt(_SOS_WIDE, x - np.mean(x))
    pk, _ = find_peaks(xb, distance=int(0.33 * FS), prominence=0.3 * np.std(xb))
    if len(pk) < 15: return None
    tr = np.array([np.argmin(xb[max(0, a - int(0.5 * FS)):a]) + max(0, a - int(0.5 * FS)) if a > 2 else a for a in pk])
    t = pk / FS; hi = xw[pk]; lo = xw[tr]
    ibi = np.diff(t); good = (ibi > 0.3) & (ibi < 2.0)
    return t, dict(iv=(hi + lo) / 2, av=hi - lo, fv=np.concatenate([[ibi[0] if len(ibi) else 0.8], ibi])), good

RAW = False
WIN = 64   # chosen on BIDMC: 64 s windows were clearly more accurate than 32 s

def breathing_rate(x):
    """Breathing rate for one 64 s PPG window (3200 samples at 50 Hz). Uses the intensity modulation (best on BIDMC);
    amplitude and interval modulations are used only to flag agreement. Returns (rate or None, info)."""
    r = beats_and_series(x)
    if r is None: return None, dict(why='too few pulses')
    t, ser, good = r
    if good.mean() < 0.8: return None, dict(why='irregular pulses')
    est = {k: _spec_peak(t, v, t[-1]) for k, v in ser.items()}
    if RAW: return None, dict(raw=est, good=float(good.mean()), nb=len(t))
    if est['iv'][0] is None: return None, dict(why='no spectrum')
    agree = any(est[k][0] is not None and abs(est[k][0] - est['iv'][0]) <= 2 for k in ('av', 'fv'))
    return est['iv'][0], dict(agree=agree, est={q: (None if v[0] is None else round(v[0], 1)) for q, v in est.items()})

def pause_candidates(t, iv, thr=0.35, min_s=10.0, base_s=60.0, gap_s=3.0, close_s=2.0):
    """Breathing pause candidates from the beat-by-beat intensity series. A candidate is a stretch where the breathing-band (0.1-0.5 Hz) amplitude
    stays below thr x its median over the previous base_s seconds for at least min_s seconds. Stretches with no pulse for gap_s are skipped.
    Returns list of (start_s, end_s). Unvalidated: no public dataset has PPG with labeled apnea events."""
    import pandas as pd
    from scipy.ndimage import uniform_filter1d
    if len(t) < 30: return []
    tg = np.arange(t[0], t[-1], 0.25); x = np.interp(tg, t, iv)
    x = sosfiltfilt(butter(2, [0.1, 0.5], btype='band', fs=4, output='sos'), x - x.mean())
    env = np.sqrt(uniform_filter1d(x ** 2, 24))                       # 6 s RMS
    base = pd.Series(env).rolling(int(base_s * 4), min_periods=int(base_s * 4)).median().shift(1).values
    gap = np.zeros(len(tg), bool)
    for a, b in zip(t[:-1], t[1:]):
        if b - a > gap_s: gap |= (tg >= a) & (tg <= b)
    low = (env < thr * base) & ~gap & np.isfinite(base)
    if close_s: from scipy.ndimage import binary_closing; low = binary_closing(np.r_[False, low, False], np.ones(int(close_s * 4), bool))[1:-1]   # bridge dips shorter than close_s
    out = []; i = 0
    while i < len(low):
        if low[i]:
            j = i
            while j < len(low) and low[j]: j += 1
            if (j - i) / 4 >= min_s: out.append((float(tg[i]), float(tg[j - 1])))
            i = j
        else: i += 1
    return out


def breath_wave(t, iv, base_s=60.0):
    """Breathing waveform (0.1-0.5 Hz band of the pulse-intensity series, 4 Hz), its 6 s RMS envelope, and the baseline used for pause detection."""
    import pandas as pd
    from scipy.ndimage import uniform_filter1d
    tg = np.arange(t[0], t[-1], 0.25); x = np.interp(tg, t, iv)
    x = sosfiltfilt(butter(2, [0.1, 0.5], btype='band', fs=4, output='sos'), x - x.mean())
    env = np.sqrt(uniform_filter1d(x ** 2, 24))
    base = pd.Series(env).rolling(int(base_s * 4), min_periods=int(base_s * 4)).median().shift(1).values
    return tg, x, env, base
