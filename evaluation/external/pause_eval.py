import sys, numpy as np, pandas as pd
sys.path.insert(0, 'nightpulse')
import resp as R
from scipy.signal import resample_poly
B='work/bidmc/'
cfgs=[(0.5,10),(0.4,10),(0.35,10),(0.25,10),(0.35,15),(0.25,15)]
tot={c:[0,0.0] for c in cfgs}; per={c:[] for c in cfgs}
for i in range(1,54):
    s=pd.read_csv(f'{B}bidmc_{i:02d}_Signals.csv');s.columns=[c.strip() for c in s.columns]
    x=resample_poly(s['PLETH'].values.astype(float),2,5);r=R.beats_and_series(x)
    if r is None: continue
    t,ser,good=r;dur=(t[-1]-t[0]-60)/3600
    for c in cfgs:
        ev=R.pause_candidates(t,ser['iv'],thr=c[0],min_s=c[1]);tot[c][0]+=len(ev);tot[c][1]+=max(dur,0);per[c].append(len(ev)>0)
for c in cfgs: print(f'thr {c[0]} min {c[1]}s: {tot[c][0]} candidates in {tot[c][1]:.1f} h of breathing = {tot[c][0]/tot[c][1]:.1f}/h ; recordings with >=1: {np.mean(per[c])*100:.0f}%')
