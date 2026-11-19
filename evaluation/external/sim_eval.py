import sys, glob, os, re, numpy as np, pandas as pd
sys.path.insert(0, 'nightpulse')
import resp as RS
from scipy.signal import decimate, butter, sosfiltfilt
from scipy.ndimage import uniform_filter1d
R = glob.glob('work/apnoea_sim/x/*/')[0]
def truth(subj, name):
    q = pd.read_csv(f'{R}Inline_PQ_Data/Subject{subj}/Subject{subj}_{name}.csv'); d = q.iloc[:, 2].values.astype(float); dt = 0.0025
    w = int(0.5 / dt); env = np.sqrt(np.maximum(uniform_filter1d((d - np.median(d)) ** 2, w), 0))[::int(0.25 / dt)]; hop = 0.25
    thr0 = 0.2 * np.percentile(env[env > 1e-3], 75) if (env > 1e-3).any() else 1
    act = np.where(env > thr0)[0]
    if not len(act): return []
    a0, a1 = act[0], act[-1]; low = env[a0:a1 + 1] <= thr0; out = []; i = 0
    while i < len(low):
        if low[i]:
            j = i
            while j < len(low) and low[j]: j += 1
            if (j - i) * hop >= 5: out.append(((a0 + i) * hop, (a0 + j) * hop))
            i = j
        else: i += 1
    return out
def ppg(subj, name, ch):
    d = pd.read_csv(f'{R}Neck_Pulse_Oximeter_Data/Subject{subj}/Subject{subj}_{name}_pulse.csv'); x = d[ch].values.astype(float)
    return decimate(x, 5, zero_phase=True)
def detect(x, base_s, thr=0.35, min_s=8.0):
    r = RS.beats_and_series(x)
    if r is None: return None
    t, ser, good = r
    return RS.pause_candidates(t, ser['iv'], thr=thr, min_s=min_s, base_s=base_s)
if __name__ == '__main__':
    chs = ['PD1', 'PD2', 'PD3', 'PD4', 'PD1_9', 'PD2_9', 'PD3_9', 'PD4_9']
    # channel choice independent of labels: share of beats found over 20 normal trials
    sc = {}
    for ch in chs:
        n = 0
        for s in range(1, 21):
            x = ppg(s, '4cmH2O_normal', ch); r = RS.beats_and_series(x); n += 0 if r is None else (len(r[0]) > 40) * 1 + (r[2].mean() if r else 0)
        sc[ch] = n
    print(sc); ch = max(sc, key=sc.get); print('channel', ch)
    for base in (12, 15, 20):
        for thr in (0.35, 0.5):
            hit = tot = fa = nt = 0; errs = []
            for s in range(1, 21):
                for p in ('0cmH2O_normal', '4cmH2O_normal', '8cmH2O_normal', '4cmH2O_apnea1', '4cmH2O_apnea2', '8cmH2O_apnea1', '8cmH2O_apnea2'):
                    try: x = ppg(s, p, ch)
                    except Exception: continue
                    c = detect(x, base, thr)
                    if c is None: continue
                    if 'normal' in p: nt += 1; fa += len(c) > 0
                    else:
                        tr = truth(s, p)
                        if not tr: continue
                        tot += 1; T = max(tr, key=lambda a: a[1] - a[0]); ov = [min(T[1], b) - max(T[0], a) for a, b in c]
                        ok = any(o > 0.5 * (T[1] - T[0]) for o in ov); hit += ok
                        if ok: a, b = c[int(np.argmax(ov))]; errs.append((a - T[0], b - T[1]))
            e = np.array(errs); print(f'base {base}s thr {thr}: detected {hit}/{tot} = {100*hit/max(tot,1):.0f}%, normal trials with false pause {fa}/{nt} = {100*fa/max(nt,1):.0f}%, start err median {np.median(e[:,0]):.1f}s end err median {np.median(e[:,1]):.1f}s' if len(e) else f'base {base} thr {thr}: none')
