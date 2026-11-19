"""NightPulse local dashboard. Serves a web page from the board; open it in a browser on the board's monitor.
Usage: python3 dashboard.py data/a01 [minutes=120]      then browse to http://localhost:8000
The data source is a replayed PhysioNet recording today; a live EVM source plugs into the same state."""
import sys, os, json, time, threading
try:
    import resource
except ImportError:                      # Windows has no resource module
    import types as _t, time as _tm
    resource = _t.SimpleNamespace(RUSAGE_SELF=0, getrusage=lambda _w: _t.SimpleNamespace(ru_maxrss=0, ru_utime=_tm.process_time(), ru_stime=0.0))
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import numpy as np, wfdb
import nightpulse as NP
import resp as RS

EXPORT_DIR = os.environ.get('NIGHTPULSE_EXPORT', 'exports')
if '--export-dir' in sys.argv:                      # python3 dashboard.py live --export-dir /media/usb/nightpulse
    i = sys.argv.index('--export-dir'); EXPORT_DIR = sys.argv[i + 1]; del sys.argv[i:i + 2]
BACKUP_DIR = os.environ.get('NIGHTPULSE_BACKUP')
if '--backup-dir' in sys.argv:                      # extra copy of the raw capture every 30 s, e.g. a USB stick
    i = sys.argv.index('--backup-dir'); BACKUP_DIR = sys.argv[i + 1]; del sys.argv[i:i + 2]
REC = sys.argv[1] if len(sys.argv) > 1 else 'data/a01'
NMIN = int(sys.argv[2]) if len(sys.argv) > 2 else 120
PORT = 8000
S = dict(mode='REPLAY', record=os.path.basename(REC), status='loading', speed=5, playhead=0.0, total_s=0,
         history=[], ecg=[], ecg_peaks=[], quality='...', quality_why='', hr=0, lat=[], model=NP.M['version'],
         ppg='no source', events=0, paused=False, test=False, msg='', resp_rate=None, resp_agree=False, resp_hist=[], pauses=[], bw=[], bw_end=0.0, export=None)
LOCK = threading.Lock()
GEN = [0]
CUR = {}
DATA_DIR = 'data' if REC == 'live' else (os.path.dirname(REC) or '.')
LIVE = 'LIVE_EVM'; LIVE_TEST = 'LIVE_TEST'; STREAM = [None]
def records():
    return [LIVE, LIVE_TEST] + sorted(f[:-4] for f in os.listdir(DATA_DIR) if f.endswith('.hea')) + sorted(f for f in os.listdir(DATA_DIR) if f.endswith('.rr'))
def start(name):
    GEN[0] += 1; g = GEN[0]
    with LOCK:
        S.update(record=name, paused=False, status='loading', playhead=0.0, total_s=0, history=[], ecg=[], ecg_peaks=[], quality='...', quality_why='', hr=0, lat=[], events=0, msg='', ppg='no source', resp_rate=None, resp_agree=False, resp_hist=[], pauses=[], bw=[], bw_end=0.0, export=None, mode='LIVE' if name in (LIVE, LIVE_TEST) else 'REPLAY', test=(name == LIVE_TEST))
    threading.Thread(target=live_worker if name in (LIVE, LIVE_TEST) else (rr_worker if name.endswith('.rr') else worker), args=(g, name == LIVE_TEST) if name in (LIVE, LIVE_TEST) else (g, os.path.join(DATA_DIR, name)), daemon=True).start()

def sysstats():
    out = {}
    try:
        with open('/proc/meminfo') as f: mi = {l.split(':')[0]: int(l.split()[1]) for l in f}
        out['ram_used_mb'] = (mi['MemTotal'] - mi['MemAvailable']) // 1024; out['ram_total_mb'] = mi['MemTotal'] // 1024
    except Exception: pass
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f: out['temp_c'] = int(f.read()) / 1000
    except Exception: pass
    return out

_last = [None]
def cpu_pct():
    try:
        with open('/proc/stat') as f: v = list(map(int, f.readline().split()[1:]))
        idle = v[3] + v[4]; tot = sum(v)
        p = _last[0]; _last[0] = (idle, tot)
        return 0.0 if p is None else round(100 * (1 - (idle - p[0]) / max(1, tot - p[1])), 1)
    except Exception: return 0.0


def score_minute(m, sig, t, ann=None):
    ts = time.perf_counter()
    b = t[(t >= m * 60) & (t < (m + 1) * 60)]; x = sig[m * 6000:(m + 1) * 6000]
    ok, why = NP.quality_ok(x, b); sc = None; hr = 0
    if ok:
        f0 = NP.minute_feats(b); hr = 60 / f0[0]
        w = NP.win_feats(t[(t >= (m - 2) * 60) & (t < (m + 3) * 60)])
        nb = []
        for k in (-1, 1, -2, 2):
            bb = t[(t >= (m + k) * 60) & (t < (m + k + 1) * 60)]; xx = sig[(m + k) * 6000:(m + k + 1) * 6000]
            nb += NP.minute_feats(bb)[:4] if (len(xx) == 6000 and NP.quality_ok(xx, bb)[0]) else [0.0] * 4
        if w is None: ok, why = False, 'short window'
        elif NP.ood(f0 + w + nb): ok, why = False, 'outside trained range'
        else: sc = NP.score(f0 + w + nb)
    return sc, hr, ok, why, (time.perf_counter() - ts) * 1000

def score_provisional(m, sig, t, end):
    """Past-only score for minute m using only data that has arrived. Missing neighbours count as zeros (as for a low-quality neighbour)."""
    ts = time.perf_counter(); b = t[(t >= m * 60) & (t < (m + 1) * 60)]; x = sig[m * 6000:(m + 1) * 6000]
    ok, why = NP.quality_ok(x, b); sc = None; hr = 0
    if ok:
        f0 = NP.minute_feats(b); hr = 60 / f0[0]
        w = NP.win_feats(t[(t >= max(0, m - 2) * 60) & (t < min(end, (m + 3) * 60))]); nb = []
        for k in (-1, 1, -2, 2):
            lo = (m + k) * 60
            if lo < 0 or lo + 60 > end: nb += [0.0] * 4; continue
            bb = t[(t >= lo) & (t < lo + 60)]; xx = sig[(m + k) * 6000:(m + k + 1) * 6000]
            nb += NP.minute_feats(bb)[:4] if (len(xx) == 6000 and NP.quality_ok(xx, bb)[0]) else [0.0] * 4
        if w is None: ok, why = False, 'short window'
        elif NP.ood(f0 + w + nb): ok, why = False, 'outside trained range'
        else: sc = NP.score(f0 + w + nb)
    return sc, hr, ok, why, (time.perf_counter() - ts) * 1000

def score_test(t):
    """Debug score from the last 20 beats only. Not a risk result."""
    b = t[-21:]; f0 = NP.minute_feats(b); w = NP.win_feats(t) or [0.0] * 4
    return NP.score(f0 + w + [0.0] * 16), 60 / f0[0]

def set_hist(e):
    for i, h in enumerate(S['history']):
        if h['m'] == e['m']: S['history'][i] = e; return
    S['history'].append(e)

def rr_gate(b):
    """Beat-only quality gate (the ESP32 path has no waveform): beat count and R-R consistency, as in the on-chip core."""
    rr = np.diff(b)
    if len(b) < 30 or len(b) > 200: return False, 'beat count'
    if np.mean((rr > 0.3) & (rr < 2.0)) < 0.9: return False, 'irregular beats'
    return True, 'ok'

def score_rr(m, t):
    ts = time.perf_counter(); sl = lambda k: t[(t >= (m + k) * 60) & (t < (m + k + 1) * 60)]
    ok, why = rr_gate(sl(0)); sc = None; hr = 0
    if ok:
        f0 = NP.minute_feats(sl(0)); hr = 60 / f0[0]; w = NP.win_feats(t[(t >= (m - 2) * 60) & (t < (m + 3) * 60)]); nb = []
        for k in (-1, 1, -2, 2): nb += NP.minute_feats(sl(k))[:4] if (m + k >= 0 and rr_gate(sl(k))[0]) else [0.0] * 4
        if w is None: ok, why = False, 'short window'
        elif NP.ood(f0 + w + nb): ok, why = False, 'outside trained range'
        else: sc = NP.score(f0 + w + nb)
    return sc, hr, ok, why, (time.perf_counter() - ts) * 1000

def read_rr(path):
    out = []
    for l in open(path, errors='ignore'):
        l = l.strip().split(',')[0]
        if l.isdigit(): out.append(int(l))
    return np.array(out) / 1000.0

def rr_worker(gen, path):
    """Replay an R-R log recorded on a microcontroller (one beat time in ms per line)."""
    t = read_rr(path); total = float(t[-1]) if len(t) else 0.0
    CUR.update(gen=gen, sig=None, t=t)
    with LOCK: S['status'] = 'running' if total >= 300 else 'error'; S['total_s'] = total; S['msg'] = 'R-R log from a microcontroller (no waveform; beats only)' if total >= 300 else 'log shorter than 5 minutes: nothing to score'; S['ppg'] = 'no source'
    scored = 1; ph = 0.0; last = time.perf_counter()
    while GEN[0] == gen and total >= 300:
        now = time.perf_counter(); dt = now - last; last = now
        with LOCK:
            if not S['paused']: ph = min(ph + dt * S['speed'], total)
            S['playhead'] = ph
        while (scored + 4) * 60 <= ph and (scored + 4) * 60 <= total:
            scored += 1; sc, hr, ok, why, ms = score_rr(scored, t)
            with LOCK:
                S['history'].append(dict(m=scored, score=sc, hr=round(hr, 1), ok=ok, why=why, label=None)); S['lat'] = (S['lat'] + [round(ms, 1)])[-60:]
                S['quality'] = 'GOOD' if ok else 'UNKNOWN'; S['quality_why'] = why
                if sc is not None and sc > 0.5: S['events'] += 1
                if hr: S['hr'] = round(hr)
        if ph >= total and (scored + 4) * 60 > total:
            with LOCK: S['status'] = 'finished'
        time.sleep(0.05)

def export_bundle(name, rawpath, ppg, test=False):
    """Everything from a stopped live session in one folder (and a zip): raw capture, TI-style CSV, 100 Hz record, minute scores, breathing report."""
    import shutil, csv
    d = os.path.join(EXPORT_DIR, name); os.makedirs(d, exist_ok=True)
    for f in (f'data/{name}_AFE4950_CAPTURED_DATA.csv', f'data/{name}.dat', f'data/{name}.hea', rawpath):
        if f and os.path.exists(f): shutil.copy(f, d)
    with LOCK: hist = [dict(h) for h in S['history']]
    with open(os.path.join(d, 'minute_scores.csv'), 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['minute', 'risk_score', 'apnea_like', 'heart_rate', 'usable', 'reason', 'provisional'])
        for h in sorted(hist, key=lambda h: h['m']): w.writerow([h['m'], '' if h['score'] is None else round(h['score'], 3), '' if h['score'] is None else int(h['score'] > 0.5), h['hr'], int(h['ok']), h['why'], int(bool(h.get('prov')))])
    npz = None
    if len(ppg) >= 90 * RS.FS:
        import analyze_session as AS
        npz = len(AS.write_report(np.asarray(ppg, float), name, d)['pauses'])
    fin = [h for h in hist if not h.get('prov') and h['score'] is not None]
    summ = dict(session=name, duration_min=round(len(ppg) / RS.FS / 60, 1) if len(ppg) else None, model=NP.M['version'], minutes_scored=len(fin),
                apnea_like_minutes=sum(1 for h in fin if h['score'] > 0.5), mean_hr=round(float(np.mean([h['hr'] for h in fin if h['hr']])), 1) if any(h['hr'] for h in fin) else None,
                breathing_pause_candidates=npz, note='Educational research prototype. Not a medical device. Pause candidates are unvalidated.' + (' TEST MODE session, scores are not risk results.' if test else ''))
    json.dump(summ, open(os.path.join(d, 'summary.json'), 'w'), indent=1)
    z = shutil.make_archive(os.path.join(EXPORT_DIR, name), 'zip', d)
    with LOCK: S['export'] = dict(name=name, dir=os.path.abspath(d), zip=os.path.abspath(z), files=len(os.listdir(d))); S['msg'] = 'Session saved to ' + os.path.abspath(d)

def live_worker(gen, test=False):
    """Live source: AFE4950EVM -> chip config -> FIFO decode -> 100 Hz ECG -> same scoring as replay."""
    import evm_live as EV
    stream = EV.EvmStream(cfg=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'evm', 'AFE4950_Settings.cfg'))
    stream.backup = BACKUP_DIR
    ppg = np.zeros(0); last_rr = 0.0; last_pz = 0.0
    sig = np.zeros(0); t = np.zeros(0); committed = 0.0; last_det = 0.0; scored = 1; tstep = 0.0; last_prov = 0.0
    try:
        while GEN[0] == gen and stream.state in ('starting', 'configuring'):
            with LOCK: S['status'] = 'connecting'; S['msg'] = stream.msg or 'looking for the EVM'
            time.sleep(0.3)
        while GEN[0] == gen:
            if stream.state == 'error':
                with LOCK: S['status'] = 'error'; S['msg'] = stream.err or 'EVM error'
                return
            new = stream.pull100()
            if len(new): sig = np.concatenate([sig, new])
            p = stream.take_ppg()
            if len(p): ppg = np.concatenate([ppg, p])
            pend = len(ppg) / RS.FS
            if pend - last_rr >= 8 and len(ppg) >= RS.WIN * RS.FS:        # breathing rate from the optical channel
                last_rr = pend; r, info = RS.breathing_rate(ppg[-RS.WIN * RS.FS:])
                with LOCK:
                    S['resp_rate'] = None if r is None else round(r, 1); S['resp_agree'] = bool(info.get('agree', False)); S['ppg'] = 'GOOD' if r is not None else 'NO PULSE'
                    if r is not None: S['resp_hist'] = (S['resp_hist'] + [round(r, 1)])[-60:]
            if pend - last_pz >= 4 and pend >= 90:                        # breathing pause candidates
                last_pz = pend; seg = ppg[-180 * RS.FS:]; off = pend - len(seg) / RS.FS; rr = RS.beats_and_series(seg) if len(seg) > 60 * RS.FS else None
                if rr is not None:
                    tb, ser, _ = rr
                    tgw, xw, ew, _b = RS.breath_wave(tb, ser['iv']); k = tgw > tgw[-1] - 120; sc = 3 * (np.median(ew[k]) + 1e-9)
                    with LOCK: S['bw'] = [round(float(v), 2) for v in np.clip(xw[k] / sc, -1.2, 1.2)]; S['bw_end'] = round(off + float(tgw[-1]), 1)
                    for a, b in RS.pause_candidates(tb, ser['iv']):
                        a += off; b += off
                        with LOCK:
                            for q in S['pauses']:
                                if a <= q['end'] + 1 and b >= q['start'] - 1: q['start'] = min(q['start'], round(a, 1)); q['end'] = max(q['end'], round(b, 1)); break
                            else: S['pauses'] = (S['pauses'] + [dict(start=round(a, 1), end=round(b, 1))])[-20:]
            end = len(sig) / NP.FS
            if end - last_det >= 2 and end > 12:
                last_det = end; ws = max(0.0, end - 90)
                pk = NP.detect(sig[int(ws * NP.FS):]) / NP.FS + ws
                pk = pk[(pk > committed) & (pk <= end - 10)]
                if len(pk): t = np.concatenate([t, pk]); committed = end - 10
            CUR.update(gen=gen, sig=sig, t=t)
            with LOCK:
                S['status'] = 'running'; S['msg'] = 'TEST MODE, not a risk result' if test else 'live from AFE4950EVM'; S['playhead'] = end; S['total_s'] = end
                if not S['paused'] and len(sig):
                    seg = sig[-600:]; S['ecg'] = [round(float(v), 3) for v in seg[::2]]
                    from scipy.signal import find_peaks
                    pk6, _ = find_peaks(seg, height=0.5 * float(seg.max()), distance=30)   # quick display-only dots; scoring uses XQRS
                    S['ecg_peaks'] = [round(float(i / NP.FS - len(seg) / NP.FS), 2) for i in pk6]
                if len(t) >= 9: S['hr'] = round(60 / float(np.mean(np.diff(t[-9:]))))
            if test:
                if len(t) >= 15 and end - tstep >= 5:
                    tstep = end; sc, hr = score_test(t)
                    with LOCK:
                        S['history'].append(dict(m=int(end // 5), score=sc, hr=round(hr, 1), ok=True, why='test', label=None, test=True))
                        S['history'] = S['history'][-60:]; S['quality'] = 'GOOD'; S['quality_why'] = 'TEST MODE'
                time.sleep(0.2); continue
            while (scored + 4) * 60 <= end:
                scored += 1; m = scored
                sc, hr, ok, why, ms = score_minute(m, sig, t)
                with LOCK:
                    set_hist(dict(m=m, score=sc, hr=round(hr, 1), ok=ok, why=why, label=None))
                    S['lat'] = (S['lat'] + [round(ms, 1)])[-60:]; S['quality'] = 'GOOD' if ok else 'UNKNOWN'; S['quality_why'] = why
                    if sc is not None and sc > 0.5: S['events'] += 1
            # provisional bars for minutes whose 2-minute lookahead has not arrived yet (refreshed every 10 s of data)
            if end - last_prov >= 10:
                last_prov = end
                for m in range(1, int(end // 60)):
                    if 1 < m <= scored: continue
                    sc, hr, ok, why, ms = score_provisional(m, sig, t, end)
                    with LOCK: set_hist(dict(m=m, score=sc, hr=round(hr, 1), ok=ok, why=why, label=None, prov=True))
            time.sleep(0.2)
    finally:
        stream.stop(); time.sleep(0.5)
        if len(sig) >= 12000:   # keep the session as a recording (raw TI-style CSV + 100 Hz record)
            name = 'live_' + time.strftime('%Y%m%d_%H%M%S'); stream.export(name); os.system(f'{sys.executable} afe_csv.py data/{name}_AFE4950_CAPTURED_DATA.csv {name} > /dev/null 2>&1')
            try: export_bundle(name, getattr(stream, 'rawpath', None), ppg, test)
            except Exception as e:
                with LOCK: S['msg'] = 'export failed: ' + str(e)

def worker(gen, REC):
    rec = wfdb.rdrecord(REC); sig = rec.p_signal[:, 0]
    try: ann = wfdb.rdann(REC, 'apn').symbol
    except Exception: ann = None
    n = min(NMIN, len(sig) // 6000 - 3)
    sig = sig[:(n + 3) * 6000]
    peaks = np.concatenate([NP.detect(sig[s:s + 60000]) + s for s in range(0, len(sig), 60000)])
    t = peaks / NP.FS
    CUR.update(gen=gen, sig=sig, t=t)
    with LOCK: S['status'] = 'running'; S['total_s'] = len(sig) / NP.FS
    scored = 1; ph = 0.0; last = time.perf_counter()
    while GEN[0] == gen:
        now = time.perf_counter(); dt = now - last; last = now
        with LOCK:
            if not S['paused']: ph = min(ph + dt * S['speed'], len(sig) / NP.FS - 1)
            S['playhead'] = ph
            i1 = int(ph * NP.FS); i0 = max(0, i1 - 600)
            seg = sig[i0:i1]
            S['ecg'] = [round(float(v), 3) for v in seg[::2]]
            S['ecg_peaks'] = [round(float(p - ph), 2) for p in t if ph - 6 <= p <= ph]
            m = scored + 1
        # score a minute once its +2 minute lookahead has been seen
        while (scored + 4) * 60 <= ph and scored + 1 < n:
            scored += 1; m = scored
            ts = time.perf_counter()
            b = t[(t >= m * 60) & (t < (m + 1) * 60)]; x = sig[m * 6000:(m + 1) * 6000]
            ok, why = NP.quality_ok(x, b); sc = None; hr = 0
            if ok:
                f0 = NP.minute_feats(b); hr = 60 / f0[0]
                w = NP.win_feats(t[(t >= (m - 2) * 60) & (t < (m + 3) * 60)])
                nb = []
                for k in (-1, 1, -2, 2):
                    bb = t[(t >= (m + k) * 60) & (t < (m + k + 1) * 60)]; xx = sig[(m + k) * 6000:(m + k + 1) * 6000]
                    nb += NP.minute_feats(bb)[:4] if (len(xx) == 6000 and NP.quality_ok(xx, bb)[0]) else [0.0] * 4
                if w is None: ok, why = False, 'short window'
                elif NP.ood(f0 + w + nb): ok, why = False, 'outside trained range'
                else: sc = NP.score(f0 + w + nb)
            ms = (time.perf_counter() - ts) * 1000
            with LOCK:
                S['history'].append(dict(m=m, score=sc, hr=round(hr, 1), ok=ok, why=why, label=(ann[m] if ann else None)))
                S['lat'] = (S['lat'] + [round(ms, 1)])[-60:]
                S['quality'] = 'GOOD' if ok else 'UNKNOWN'; S['quality_why'] = why
                if sc is not None and sc > 0.5: S['events'] += 1
                if hr: S['hr'] = round(hr)
        if scored + 1 >= n and ph >= len(sig) / NP.FS - 2:
            with LOCK: S['status'] = 'finished'
        time.sleep(0.05)

HTML = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dashboard.html')).read() if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dashboard.html')) else '<h1>dashboard.html missing</h1>'

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        if self.path.startswith('/api/upload'):
            n = min(int(self.headers.get('Content-Length', 0)), 8_000_000); raw = self.rfile.read(n).decode('utf-8', 'ignore')
            q = self.path.split('name=')[-1] if 'name=' in self.path else 'upload_%d' % int(time.time())
            name = ''.join(c for c in q if c.isalnum() or c in '_-')[:40] or 'upload'; fn = name + '.rr'
            os.makedirs(DATA_DIR, exist_ok=True); open(os.path.join(DATA_DIR, fn), 'w').write(raw)
            cnt = sum(1 for l in raw.splitlines() if l.strip().split(',')[0].isdigit()); body = json.dumps(dict(name=fn, beats=cnt)).encode()
            if cnt >= 30: start(fn)
        else: body = b'{}'
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path.startswith('/api/state'):
            with LOCK: d = dict(S)
            d['sys'] = sysstats(); d['sys']['cpu'] = cpu_pct()
            d['proc_cpu_s'] = round(time.process_time(), 1); d['proc_rss_mb'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
            body = json.dumps(d).encode(); ct = 'application/json'
        elif self.path.startswith('/api/pause') or self.path.startswith('/api/resume'):
            with LOCK: S['paused'] = self.path.startswith('/api/pause')
            body = b'{}'; ct = 'application/json'
        elif self.path.startswith('/api/stop'):
            GEN[0] += 1
            with LOCK: S.update(status='stopped', paused=False)
            body = b'{}'; ct = 'application/json'
        elif self.path.startswith('/api/play'):
            start(S['record']); body = b'{}'; ct = 'application/json'
        elif self.path.startswith('/api/minute/'):
            m = int(self.path.split('/')[-1]); d = {}
            if CUR.get('sig') is not None:
                sg, tt = CUR['sig'], CUR['t']; a = m * 6000 + 1500; seg = sg[a:a + 600]
                pk = tt[(tt * NP.FS >= a) & (tt * NP.FS < a + 600)] - (a + 600) / NP.FS
                d = dict(ecg=[round(float(v), 3) for v in seg[::2]], peaks=[round(float(p), 2) for p in pk], start_s=a / NP.FS)
            body = json.dumps(d).encode(); ct = 'application/json'
        elif self.path.startswith('/api/export.zip'):
            ex = S.get('export')
            if not ex or not os.path.exists(ex['zip']): self.send_response(404); self.end_headers(); return
            body = open(ex['zip'], 'rb').read(); self.send_response(200); self.send_header('Content-Type', 'application/zip'); self.send_header('Content-Disposition', f'attachment; filename="{ex["name"]}.zip"')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body); return
        elif self.path.startswith('/api/records'):
            body = json.dumps(records()).encode(); ct = 'application/json'
        elif self.path.startswith('/api/select/'):
            name = self.path.split('/')[-1]
            if name in records(): start(name)
            body = b'{}'; ct = 'application/json'
        elif self.path.startswith('/api/speed/'):
            with LOCK: S['speed'] = max(1, min(60, int(self.path.split('/')[-1])))
            body = b'{}'; ct = 'application/json'
        else: body = HTML.encode(); ct = 'text/html; charset=utf-8'
        self.send_response(200); self.send_header('Content-Type', ct); self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

if __name__ == '__main__':
    start(LIVE if REC == 'live' else os.path.basename(REC))
    print(f'NightPulse dashboard on http://localhost:{PORT}  (replaying {REC}, {NMIN} min)'); sys.stdout.flush()
    ThreadingHTTPServer(('0.0.0.0', PORT), H).serve_forever()
