import pickle, numpy as np, pandas as pd, itertools, sys
from scipy.ndimage import binary_closing
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
D = 'work/osasud/'
F = pickle.load(open(D + 'ppg_feats.pkl', 'rb'))
def runs(a, min_s=10):
    z = np.diff(np.r_[0, a.astype(int), 0]); st = np.where(z == 1)[0]; en = np.where(z == -1)[0]; return [(int(x), int(y)) for x, y in zip(st, en) if y - x >= min_s]
EV = {}
for p, r in F.items():
    e = r['ev']; EV[p] = dict(apn=runs(np.array([s.startswith('APNEA') for s in e])), hyp=runs(np.array([s == 'HYPOPNEA' for s in e])), hours=sum(len(s['tg']) for s in r['segs']) / 4 / 3600)
_base = {}
def base_of(p, base_s, q):
    k = (p, base_s, q)
    if k not in _base:
        _base[k] = [pd.Series(s['env']).rolling(int(base_s * 4), min_periods=int(base_s * 4)).quantile(q).shift(1).values for s in F[p]['segs']]
    return _base[k]
def cands(p, thr, min_s, base_s=60, q=0.5, close_s=2.0):
    out = []
    for s, b in zip(F[p]['segs'], base_of(p, base_s, q)):
        ratio = s['env'] / b; low = (ratio < thr) & ~s['gap'] & np.isfinite(ratio)
        if close_s: low = binary_closing(np.r_[False, low, False], np.ones(int(close_s * 4), bool))[1:-1]
        i = 0
        while i < len(low):
            if low[i]:
                j = i
                while j < len(low) and low[j]: j += 1
                if (j - i) / 4 >= min_s: out.append((float(s['tg'][i]), float(s['tg'][j - 1])))
                i = j
            else: i += 1
    return out
def ovl(c, evs, tol): return any(c[0] <= e1 + tol and c[1] >= e0 - tol for e0, e1 in evs)
def evaluate(pats, **kw):
    na = ha = nh = hh = nc = tc = 0; hrs = 0; fp = 0; per = []
    for p in pats:
        C = cands(p, **kw); a, h = EV[p]['apn'], EV[p]['hyp']; hrs += EV[p]['hours']
        for e in a: na += 1; ha += any(c[0] <= e[1] + 2 and c[1] >= e[0] - 2 for c in C)
        for e in h: nh += 1; hh += any(c[0] <= e[1] + 2 and c[1] >= e[0] - 2 for c in C)
        for c in C: nc += 1; tc += ovl(c, a + h, 5); fp += not ovl(c, a + h, 5)
        per.append((p, len(C) / max(EV[p]['hours'], 1e-9), (len(a) + len(h)) / max(EV[p]['hours'], 1e-9), len(a) / max(EV[p]['hours'], 1e-9)))
    return dict(sens_apnea=ha / max(na, 1), sens_hyp=hh / max(nh, 1), precision=tc / max(nc, 1), fp_per_h=fp / max(hrs, 1e-9), cands=nc, per=per, na=na)
if __name__ == '__main__':
    ids = sorted(F, key=int); dev = [p for p in ids if int(p) % 2 == 1]; test = [p for p in ids if int(p) % 2 == 0]
    rows = []
    for base_s, q, thr, min_s in itertools.product((60, 120, 300), (0.5, 0.75), (0.25, 0.35, 0.5), (8, 10, 15)):
        r = evaluate(dev, thr=thr, min_s=min_s, base_s=base_s, q=q); f1 = 2 * r['precision'] * r['sens_apnea'] / max(r['precision'] + r['sens_apnea'], 1e-9)
        rows.append((f1, base_s, q, thr, min_s, r)); 
    rows.sort(key=lambda x: -x[0])
    print('DEV top configs (F1 of precision and apnea sensitivity):')
    for f1, b, q, t, m, r in rows[:8]: print(f'  base {b}s q{q} thr {t} min {m}s: F1 {f1:.2f} sens_apnea {r["sens_apnea"]:.2f} sens_hyp {r["sens_hyp"]:.2f} precision {r["precision"]:.2f} FP/h {r["fp_per_h"]:.1f} cands {r["cands"]}')
    cur = evaluate(dev, thr=0.35, min_s=10, base_s=60, q=0.5); print('current config (thr .35, 10 s, 60 s median) on dev:', {k: round(v, 2) for k, v in cur.items() if k in ('sens_apnea', 'sens_hyp', 'precision', 'fp_per_h')})
    f1, b, q, t, m, _ = rows[0]; print('CHOSEN on dev:', b, q, t, m)
    for name, pats in (('TEST (held-out even patients)', test), ('DEV', dev)):
        r = evaluate(pats, thr=t, min_s=m, base_s=b, q=q); r0 = evaluate(pats, thr=0.35, min_s=10, base_s=60, q=0.5)
        print(name, 'chosen: sens_apnea %.2f sens_hyp %.2f precision %.2f FP/h %.1f (%d candidates, %d apnea events)' % (r['sens_apnea'], r['sens_hyp'], r['precision'], r['fp_per_h'], r['cands'], r['na']))
        print(name, 'current: sens_apnea %.2f sens_hyp %.2f precision %.2f FP/h %.1f' % (r0['sens_apnea'], r0['sens_hyp'], r0['precision'], r0['fp_per_h']))
        per = np.array([x[1:] for x in r['per']]); print('  patient level: Spearman(candidates/h, true event index/h) = %.2f' % spearmanr(per[:, 0], per[:, 1])[0], ' Spearman vs apnea index = %.2f' % spearmanr(per[:, 0], per[:, 2])[0])
        yy = per[:, 1] >= 15
        if yy.any() and (~yy).any(): print('  AUROC candidates/h for AHI>=15: %.2f (n=%d, %d positive)' % (roc_auc_score(yy, per[:, 0]), len(yy), yy.sum()))
