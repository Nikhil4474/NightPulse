import numpy as np, wfdb, glob, json, time
from scipy.signal import welch
from scipy.interpolate import interp1d
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score, f1_score, confusion_matrix
FS=100
recs=sorted(set(f[:-4] for f in glob.glob('[abc]??.apn')))
grp=lambda r:'c05c06' if r in('c05','c06') else r
def qual(x,b):
    # raw-signal quality gate for one minute: flatline, clipping, beat count, RR consistency
    if np.ptp(x)<1e-3 or np.std(x)<1e-3: return False
    if np.mean(np.abs(x)>=np.abs(x).max()*0.999)>0.02: return False
    rr=np.diff(b)
    if len(b)<30 or len(b)>200: return False
    if np.mean((rr>0.3)&(rr<2.0))<0.9: return False
    return True
def minute_feats(b):
    rr=np.diff(b);m=(rr>0.3)&(rr<2.0);rr=rr[m];d=np.diff(rr)
    return [rr.mean(),rr.std(),np.sqrt(np.mean(d**2)),np.mean(np.abs(d)>0.05),rr.std()/rr.mean(),rr.min(),rr.max(),np.percentile(rr,90)-np.percentile(rr,10),len(rr)]
def win_feats(b):
    rr=np.diff(b);tt=b[1:];m=(rr>0.3)&(rr<2.0)
    if m.sum()<100: return None
    rr=rr[m];tt=tt[m];t4=np.arange(tt[0],tt[-1],0.25);x=interp1d(tt,rr,fill_value='extrapolate')(t4)
    f,p=welch(x-x.mean(),fs=4,nperseg=min(len(x),512))
    bd=lambda lo,hi:p[(f>=lo)&(f<hi)].sum();tot=bd(0.0033,0.4)+1e-9
    return [bd(0.01,0.04)/tot,bd(0.04,0.15)/tot,bd(0.15,0.4)/tot,np.log(bd(0.01,0.04)+1e-9)]
X=[];y=[];g=[];ok=[];beat_err=[]
for r in recs:
    a=wfdb.rdann(r,'apn');ref=wfdb.rdann(r,'qrs').sample
    sig=wfdb.rdrecord(r).p_signal[:,0];pk=np.load(f'peaks_{r}.npy');t=pk/FS
    # detector agreement with PhysioNet reference beats (±50 ms)
    j=np.searchsorted(pk,ref);j=np.clip(j,1,len(pk)-1)
    near=np.minimum(np.abs(pk[j]-ref),np.abs(pk[j-1]-ref));beat_err.append((near<=5).mean())
    lab=np.array([1 if s=='A' else 0 for s in a.symbol]);n=len(lab);mq=[]
    for m in range(n):
        b=t[(t>=m*60)&(t<(m+1)*60)];xs=sig[m*6000:(m+1)*6000]
        mq.append(minute_feats(b) if (len(xs)==6000 and qual(xs,b)) else None)
    for m in range(n):
        f0=mq[m];w=None
        if f0 is not None: w=win_feats(t[(t>=(m-2)*60)&(t<(m+3)*60)])
        nb=[]
        for k in(-1,1,-2,2):
            jx=m+k;nb+=(mq[jx][:4] if 0<=jx<n and mq[jx] is not None else [0.0]*4)
        if f0 is None or w is None: X.append([0.0]*29);ok.append(False)
        else: X.append(f0+w+nb);ok.append(True)
        y.append(lab[m]);g.append(grp(r))
X=np.array(X,float);y=np.array(y);g=np.array(g);ok=np.array(ok)
idx=np.where(ok)[0]
P=np.zeros(len(y))
mk=lambda:make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000,class_weight='balanced',C=0.5))
for tr,te in GroupKFold(5).split(idx,y[idx],g[idx]):
    m=mk().fit(X[idx[tr]],y[idx[tr]]);P[idx[te]]=m.predict_proba(X[idx[te]])[:,1]
yy=y[idx];pp=P[idx];pred=(pp>0.5).astype(int);tn,fp,fn,tp=confusion_matrix(yy,pred).ravel()
res=dict(detector_beat_agreement=float(np.mean(beat_err)),minutes=int(len(y)),usable=int(ok.sum()),abstain_rate=float(1-ok.mean()),
 auroc=float(roc_auc_score(yy,pp)),sensitivity=float(tp/(tp+fn)),specificity=float(tn/(tn+fp)),f1=float(f1_score(yy,pred)),accuracy=float((pred==yy).mean()),
 fp_windows_per_hour_normal=float(fp/((tn+fp)/60)),features=29)
print(json.dumps(res,indent=1));json.dump(res,open('v3_results.json','w'),indent=1)
np.savez('feats_v3.npz',X=X,y=y,g=g,ok=ok,P=P)
final=mk().fit(X[idx],yy);import pickle;pickle.dump(final,open('model_v3.pkl','wb'))
