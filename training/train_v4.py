"""Train the deployed NightPulse model (nightpulse-lr-v4) and optionally check it against nightpulse/model.json.

Inputs (already in the repo, produced by extract_beats.py + extract_features_cv.py and wesad_feats.py):
  training/features/apnea_ecg_learning_feats.npz   29 features per minute, Apnea-ECG learning set a01-c10 (labels y, record group g, usable flag ok)
  training/features/wesad_feats.npz                29 features per minute, WESAD (flag ok, protocol state)
Recipe: apnea minutes (ok) + WESAD minutes with state <= 4 (awake, labelled non-apnea), clip each feature to its 1st-99th percentile,
StandardScaler, LogisticRegression(C=0.5, class_weight='balanced'). OOD limits are the 0.5th and 99.5th percentiles.
Usage (repo root):  python3 training/train_v4.py [--write nightpulse/model.json]
"""
import sys, json, numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
a = np.load('training/features/apnea_ecg_learning_feats.npz'); w = np.load('training/features/wesad_feats.npz')
Xa, ya = a['X'][a['ok']], a['y'][a['ok']]
Xw = w['X'][w['ok'] & (w['state'] <= 4)]
X = np.vstack([Xa, Xw]); y = np.r_[ya, np.zeros(len(Xw))]
print('apnea-ECG minutes', len(Xa), '| WESAD minutes', len(Xw), '| total', len(X))
lo, hi = np.percentile(X, 1, axis=0), np.percentile(X, 99, axis=0)
sc = StandardScaler().fit(np.clip(X, lo, hi))
clf = LogisticRegression(max_iter=3000, class_weight='balanced', C=0.5).fit(sc.transform(np.clip(X, lo, hi)), y)
new = json.load(open('nightpulse/model.json'))   # keep version and any non-trained fields
new.update(mean=sc.mean_.tolist(), scale=sc.scale_.tolist(), coef=clf.coef_[0].tolist(), intercept=float(clf.intercept_[0]),
           clip_lo=lo.tolist(), clip_hi=hi.tolist(), ood_lo=np.percentile(X, .5, axis=0).tolist(), ood_hi=np.percentile(X, 99.5, axis=0).tolist())
old = json.load(open('nightpulse/model.json'))
for k in ('mean', 'scale', 'coef', 'clip_lo', 'clip_hi', 'ood_lo', 'ood_hi'):
    print(k, 'max abs diff vs shipped model.json: %.3g' % np.abs(np.array(new[k]) - np.array(old[k])).max())
print('intercept diff: %.3g' % abs(new['intercept'] - old['intercept']))
if '--write' in sys.argv:
    json.dump(new, open(sys.argv[sys.argv.index('--write') + 1], 'w')); print('written')
