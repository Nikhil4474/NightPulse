import wfdb, numpy as np, sys, glob, os
from wfdb import processing
from multiprocessing import Pool
def run(r):
    out=f'peaks_{r}.npy'
    if os.path.exists(out): return r
    rec=wfdb.rdrecord(r); x=rec.p_signal[:,0]
    # xqrs per 10-minute chunk for robustness
    peaks=[]; step=60000
    for s in range(0,len(x),step):
        seg=x[s:s+step]
        try:
            q=processing.XQRS(sig=seg,fs=100); q.detect(verbose=False); p=q.qrs_inds+s
        except Exception: p=np.array([],int)
        peaks.append(p)
    np.save(out,np.concatenate(peaks)); return r
if __name__=='__main__':
    recs=sorted(set(f[:-4] for f in glob.glob('[abc]??.apn')))
    with Pool(2) as p:
        for r in p.imap_unordered(run,recs): print(r,flush=True)
