import pandas as pd, numpy as np, pickle
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from scipy.stats import spearmanr
P = 'work/'
df = pd.read_pickle(P + 'osasud/minutes.pkl'); df = df[df.ok == 1].copy(); df['p'] = df.p.astype(int)
BR = ['r_mean', 'r_lt50', 'r_lt35', 'r_min', 'r_std', 'a_mean', 'a_cv', 'a_min']       # breathing / pulse-amplitude features
PR = ['rr_mean', 'rr_sd', 'rr_rmssd', 'rr_pnn', 'rr_cv', 'rr_rng', 'w_vlf', 'w_lf', 'w_hf', 'w_lvl', 'c_amp', 'c_iv']   # pulse-rate variability + cyclic variation
both = df[df.ecg.notna()].copy(); print('minutes with pulse', len(df), 'with pulse and ECG score', len(both), 'positive %.0f%%' % (100 * both.y.mean()))
def lopo(d, feats, model='lr', C=0.3):
    out = np.zeros(len(d)); pats = d.p.values
    for p in np.unique(pats):
        tr, te = pats != p, pats == p
        m = make_pipeline(SimpleImputer(strategy='median'), StandardScaler(), LogisticRegression(C=C, class_weight='balanced', max_iter=2000)) if model == 'lr' else HistGradientBoostingClassifier(max_depth=3, learning_rate=0.08, max_iter=150, class_weight='balanced')
        m.fit(d.loc[tr, feats], d.y[tr]); out[te] = m.predict_proba(d.loc[te, feats])[:, 1]
    return out
def rep(name, d, s):
    auc = roc_auc_score(d.y, s); pr = s > 0.5 if name != 'ECG model alone (as shipped)' else s > 0.5
    # patient level: mean predicted prob per patient vs true event index (events per hour of labeled minutes)
    g = pd.DataFrame(dict(p=d.p.values, s=s, y=d.y.values)).groupby('p').agg(s=('s', 'mean'), y=('y', 'mean'))
    print(f'{name:42s} minute AUROC {auc:.3f} | sens {((pr) & (d.y == 1)).sum() / (d.y == 1).sum():.2f} spec {((~pr) & (d.y == 0)).sum() / (d.y == 0).sum():.2f} | patient-level Spearman {spearmanr(g.s, g.y)[0]:.2f}, AUROC (>=30% event minutes) {roc_auc_score(g.y >= 0.3, g.s) if (g.y >= 0.3).any() and (g.y < 0.3).any() else float("nan"):.2f}')
    return g
rep('ECG model alone (as shipped)', both, both.ecg.values)
for nm, f in (('Breathing/pulse-amplitude only', BR), ('Pulse-rate variability only (like ECG)', PR), ('Breathing + pulse-rate', BR + PR), ('ECG score + breathing', ['ecg'] + BR), ('ECG score + breathing + pulse-rate', ['ecg'] + BR + PR)):
    rep(nm + ' (LR)', both, lopo(both, f))
rep('Breathing + pulse-rate (HGB)', both, lopo(both, BR + PR, 'hgb')); rep('ECG score + breathing + pulse-rate (HGB)', both, lopo(both, ['ecg'] + BR + PR, 'hgb'))
rep('ECG score alone recalibrated (LR)', both, lopo(both, ['ecg']))
print('--- apnea-only minutes (hypopnea excluded from positives, hypopnea-only minutes dropped)')
d2 = both[~((both.y == 1) & (both.ya == 0))].copy(); d2['y'] = d2.ya
print('positives %.0f%% of %d' % (100 * d2.y.mean(), len(d2)))
rep('ECG as shipped', d2, d2.ecg.values); rep('Breathing + pulse-rate (HGB)', d2, lopo(d2, BR + PR, 'hgb')); rep('ECG + breathing + pulse-rate (HGB)', d2, lopo(d2, ['ecg'] + BR + PR, 'hgb'))
