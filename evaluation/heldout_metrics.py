"""Usage: python3 evaluation/heldout_metrics.py <dir with x*.pkl from heldout_run.py>"""
import pickle, numpy as np, glob, json, sys
from sklearn.metrics import roc_auc_score
R = {f[-8:-4]: pickle.load(open(f, 'rb')) for f in sorted(glob.glob(sys.argv[1].rstrip('/') + '/x*.pkl'))}
print(len(R), 'records')
S, Y, G, tot, ab = [], [], [], 0, 0
per = {}
for r, rows in R.items():
    tot += len(rows); ab += sum(1 for x in rows if x[1] is None)
    for m, sc, why, y in rows:
        if sc is not None: S.append(sc); Y.append(y); G.append(r)
    sc = np.array([x[1] for x in rows if x[1] is not None]); lab = np.array([x[3] for x in rows if x[1] is not None])
    per[r] = (len(rows), lab.sum(), (sc > .5).mean() if len(sc) else 0, np.mean(sc) if len(sc) else 0, sum(1 for x in rows if x[3]))
S, Y, G = np.array(S), np.array(Y), np.array(G)
p = S > .5; tp = (p & Y).sum(); tn = (~p & ~Y).sum(); fp = (p & ~Y).sum(); fn = (~p & Y).sum()
print('minutes', tot, 'scored', len(S), 'abstained %.1f%%' % (100 * ab / tot), 'apnea prevalence %.1f%%' % (100 * Y.mean()))
print('AUROC %.3f' % roc_auc_score(Y, S)); print('sens %.3f spec %.3f acc %.3f ppv %.3f npv %.3f' % (tp / (tp + fn), tn / (tn + fp), (tp + tn) / len(S), tp / (tp + fp), tn / (tn + fn)), dict(tp=int(tp), fn=int(fn), tn=int(tn), fp=int(fp)))
rng = np.random.default_rng(0); recs = sorted(R); au = []
for _ in range(1000):
    pick = rng.choice(recs, len(recs)); idx = np.concatenate([np.where(G == r)[0] for r in pick])
    if Y[idx].min() != Y[idx].max(): au.append(roc_auc_score(Y[idx], S[idx]))
print('AUROC 95%% CI (record bootstrap) %.3f-%.3f' % tuple(np.percentile(au, [2.5, 97.5])))
# record level (challenge definition: >=100 apnea min = apnea, <=5 = normal)
cls = {r: 'A' if v[4] >= 100 else 'N' if v[4] <= 5 else 'B' for r, v in per.items()}
print('record classes', {c: sum(1 for v in cls.values() if v == c) for c in 'ANB'})
fl = np.array([per[r][2] for r in recs]); ytrue = np.array([cls[r] == 'A' for r in recs]); keep = np.array([cls[r] != 'B' for r in recs])
print('record-level AUROC A vs N (flagged share): %.3f' % roc_auc_score(ytrue[keep], fl[keep]))
from scipy.stats import spearmanr
print('Spearman flagged share vs true apnea share across records: %.2f' % spearmanr(fl, [per[r][1] / max(1, per[r][0]) for r in recs])[0])
print('Spearman, reference share over ALL labeled minutes (definition used in report Figure 3): %.2f' % spearmanr(fl, [per[r][4] / max(1, per[r][0]) for r in recs])[0])
for t in (0.4, 0.5, 0.6): q = S > t; print('thr', t, 'sens %.2f spec %.2f' % ((q & Y).sum() / Y.sum(), (~q & ~Y).sum() / (~Y).sum()))
for r in recs: print(r, cls[r], 'true apnea min', per[r][4], 'flagged %.0f%%' % (100 * per[r][2]), 'mean score %.2f' % per[r][3])
