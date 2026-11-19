import pickle, glob, json, numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from sklearn.metrics import roc_curve, roc_auc_score
from scipy.stats import spearmanr
import sys; X = (sys.argv[1] if len(sys.argv) > 1 else 'work/xeval').rstrip('/') + '/'   # per-record pickles from evaluation/heldout_run.py
import os; os.makedirs('figs', exist_ok=True)   # figures are written to ./figs
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#555','axes.labelcolor':'#222','xtick.color':'#333','ytick.color':'#333'})
INK='#1b2733'; TEAL='#0f8b8d'; AMB='#c77d0a'; RED='#b3261e'; GRY='#8a96a3'; LT='#e8eef3'
R={f.split('/')[-1][:3]:pickle.load(open(f,'rb')) for f in sorted(glob.glob(X+'x*.pkl'))}
S,Y,G=[],[],[]
per={}
for r,rows in R.items():
    for m,sc,why,y in rows:
        if sc is not None: S.append(sc);Y.append(bool(y));G.append(r)
    sc=[x[1] for x in rows if x[1] is not None]; per[r]=dict(n=len(rows),apn=sum(1 for x in rows if x[3]),flag=float(np.mean(np.array(sc)>.5)) if sc else 0)
S,Y,G=np.array(S),np.array(Y),np.array(G)
# ---- ROC
fpr,tpr,th=roc_curve(Y,S); auc=roc_auc_score(Y,S)
fig,ax=plt.subplots(figsize=(4.6,4.2),dpi=220)
ax.plot([0,1],[0,1],ls='--',c=GRY,lw=1,label='Chance (AUROC 0.5)')
ax.plot(fpr,tpr,c=TEAL,lw=2.2,label=f'NightPulse v4 (AUROC {auc:.3f})')
for t,mk,off in ((0.4,'s',(8,-14)),(0.5,'o',(8,-14)),(0.6,'^',(8,-14))):
    p=S>t; se=(p&Y).sum()/Y.sum(); fp=(p&~Y).sum()/(~Y).sum()
    ax.scatter(fp,se,s=46,c=INK,marker=mk,zorder=5); ax.annotate(f'thr {t}',(fp,se),textcoords='offset points',xytext=off,fontsize=8,color=INK)
ax.set_xlabel('False positive rate (1 - specificity)'); ax.set_ylabel('True positive rate (sensitivity)')
ax.set_xlim(0,1); ax.set_ylim(0,1.02); ax.legend(loc='lower right',frameon=False); ax.grid(alpha=.25)
fig.tight_layout(); fig.savefig('figs/fig_roc.png'); plt.close(fig)
# ---- per record scatter
recs=sorted(per); ts=np.array([per[r]['apn']/per[r]['n'] for r in recs]); fl=np.array([per[r]['flag'] for r in recs]); apn=np.array([per[r]['apn'] for r in recs])
cls=np.array(['A' if a>=100 else 'N' if a<=5 else 'B' for a in apn])
rho=spearmanr(ts,fl)[0]
fig,ax=plt.subplots(figsize=(4.6,4.2),dpi=220)
for c,col,lab in (('A',RED,'Apnea record (>=100 apnea min)'),('B',AMB,'Borderline'),('N',TEAL,'Normal record (<=5 apnea min)')):
    m=cls==c; ax.scatter(100*ts[m],100*fl[m],c=col,s=34,label=lab,edgecolor='white',lw=.6)
for r,x,y in zip(recs,ts,fl):
    if r in ('x15','x26','x14'): ax.annotate(r,(100*x,100*y),textcoords='offset points',xytext=(5,-9),fontsize=8,color=INK)
ax.plot([0,100],[0,100],ls='--',c=GRY,lw=1)
ax.set_xlabel('Reference apnea minutes in record (%)'); ax.set_ylabel('Minutes flagged apnea-like by NightPulse (%)')
ax.set_xlim(-2,100); ax.set_ylim(-2,100); ax.legend(frameon=False,fontsize=7.5,loc='upper left'); ax.grid(alpha=.25)
ax.text(98,4,f'Spearman rho = {rho:.2f}',ha='right',fontsize=8.5,color=INK)
fig.tight_layout(); fig.savefig('figs/fig_records.png'); plt.close(fig)
print('rho',rho)
# ---- example timelines
def tl(ax,r,title):
    rows=R[r]; m=np.array([x[0] for x in rows]); sc=np.array([np.nan if x[1] is None else x[1] for x in rows]); y=np.array([x[3] for x in rows],bool)
    for a,b in zip(m[y],m[y]+1): ax.axvspan(a/60,b/60,color=RED,alpha=.13,lw=0)
    ax.plot(m/60,sc,c=TEAL,lw=1.1); ax.axhline(.5,c=INK,ls=':',lw=1)
    unk=np.isnan(sc); ax.scatter(m[unk]/60,np.full(unk.sum(),-.04),c=GRY,s=6,marker='|')
    ax.set_ylim(-.1,1.02); ax.set_ylabel('Risk score'); ax.set_title(title,loc='left',fontsize=9,color=INK); ax.grid(alpha=.2)
fig,axs=plt.subplots(2,1,figsize=(6.4,4.2),dpi=220,sharex=False)
tl(axs[0],'x05','Test record x05 (apnea record: shaded = reference apnea minutes)'); tl(axs[1],'x04','Test record x04 (normal record)')
axs[1].set_xlabel('Time since recording start (hours)')
from matplotlib.lines import Line2D
fig.legend(handles=[Line2D([],[],c=TEAL,lw=1.3,label='Per-minute risk score'),Line2D([],[],c=INK,ls=':',lw=1,label='Threshold 0.5'),Line2D([],[],c=GRY,marker='|',ls='',label='UNKNOWN (abstained)'),plt.Rectangle((0,0),1,1,fc=RED,alpha=.2,label='Reference apnea minute')],loc='lower center',ncol=4,frameon=False,fontsize=7.8)
fig.tight_layout(rect=(0,.07,1,1)); fig.savefig('figs/fig_timeline.png'); plt.close(fig)
# ---- cross dataset
fig,ax=plt.subplots(figsize=(6.4,3.4),dpi=220)
labs=['Apnea-ECG test\n(held out, ECG model)','Apnea-ECG\ncross-validation','OSASUD\nECG model','OSASUD\nPPG+pulse-rate (HGB)','OSASUD\nECG+PPG (HGB)']
vals=[.858,.809,.564,.676,.673]; cols=[TEAL,TEAL,AMB,GRY,GRY]
err=[[.858-.784,.809-.72,0,0,0],[.921-.858,.881-.809,0,0,0]]
b=ax.bar(range(5),vals,color=cols,width=.62)
ax.errorbar([0,1],vals[:2],yerr=[err[0][:2],err[1][:2]],fmt='none',ecolor=INK,capsize=3,lw=1)
tops=[.921,.881,.564,.676,.673]
for i,v in enumerate(vals): ax.text(i,tops[i]+.02,f'{v:.2f}',ha='center',fontsize=9,color=INK)
ax.axhline(.5,c=INK,ls='--',lw=1); ax.text(4.45,.51,'chance',fontsize=8,ha='right',va='bottom',color=INK)
ax.set_xticks(range(5)); ax.set_xticklabels(labs,fontsize=7.6); ax.set_ylim(0,1.05); ax.set_ylabel('AUROC (per minute)'); ax.grid(axis='y',alpha=.25)
fig.tight_layout(); fig.savefig('figs/fig_cross.png'); plt.close(fig)
# ---- architecture
fig,ax=plt.subplots(figsize=(7.0,4.4),dpi=220); ax.set_xlim(0,100); ax.set_ylim(-6,58); ax.axis('off')
def box(x,y,w,h,t,fc='#fff',ec=INK,fs=8,bold=False,tc=INK):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.3,rounding_size=1.2',fc=fc,ec=ec,lw=1.1)); ax.text(x+w/2,y+h/2,t,ha='center',va='center',fontsize=fs,color=tc,fontweight='bold' if bold else 'normal',linespacing=1.25)
def arr(x1,y1,x2,y2,c=INK,ls='-'): ax.add_patch(FancyArrowPatch((x1,y1),(x2,y2),arrowstyle='-|>',mutation_scale=9,lw=1.1,color=c,ls=ls))
ax.add_patch(FancyBboxPatch((19,14),80,42,boxstyle='round,pad=0.3,rounding_size=1.5',fc=LT,ec=GRY,lw=1)); ax.text(59,53.2,'SK-AM62B (Linux, Python, offline)',ha='center',fontsize=8.8,fontweight='bold',color=INK)
box(0.5,33,14,14,'AFE4950EVM\nECG 500 Hz\nPPG (TIA)\n50 Hz')
arr(15.2,40,21.5,40); ax.text(18.3,42.3,'USB',ha='center',fontsize=7.5,color=INK)
box(22,38.5,17,8,'Decode +\nsave raw capture',fs=7.5); box(45,38.5,17,8,'Resample 100 Hz,\n0.5-35 Hz band-pass',fs=7.5); box(68,38.5,17,8,'XQRS beat\ndetection',fs=7.5)
box(68,26,17,8,'Quality gate\n(flat, clipped,\nirregular beats)',fs=7.2); box(45,26,17,8,'29 features\n(R-R, spectral,\nneighbor minutes)',fs=7.2); box(22,26,17,8,'Logistic regression\n+ range guard',fs=7.2)
arr(39.4,42.5,44.6,42.5); arr(62.4,42.5,67.6,42.5); arr(76.5,38,76.5,34.4); arr(67.6,30,62.4,30); arr(44.6,30,39.4,30)
box(22,17.5,30,5.5,'ECG path (validated):\nscore 0-1 or UNKNOWN',fc='#e3f3f3',ec=TEAL,fs=7,bold=True); arr(30.5,25.6,30.5,23.4,c=TEAL)
box(57,17.5,38,5.5,'PPG path (experimental), from the optical\nchannel: breathing rate, pause candidates',fc='#fbf0dc',ec=AMB,fs=7)
box(22,1.5,73,8.5,'Local web dashboard\nrisk gauge, timeline, breathing graph, export, backup',fc='#fff',fs=7.4,bold=True)
arr(37,13.6,37,10.6); arr(76.5,13.6,76.5,10.6,c=AMB,ls='--')
ax.text(58,-3.5,'The same model also runs on an ESP32-S3 (C++ port with LCD gauge and WiFi dashboard).',ha='center',fontsize=7.6,style='italic',color=INK)
fig.tight_layout(pad=.3); fig.savefig('figs/fig_arch.png'); plt.close(fig)
print('ok')
