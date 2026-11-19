"""Breathing analysis of a saved EVM session. Usage: python3 analyze_session.py data/live_XXXX.raw   (or the TI style CSV)
Writes <name>_report.html (open in any browser: breathing waveform with pause candidates, breathing rate, pulse quality) and <name>_pauses.csv.
Pause candidates are unvalidated; compare them with your own notes or a pulse oximeter log."""
import sys, os, json, numpy as np
import resp as RS

def load_ppg(p):
    if p.endswith('.raw'):
        from evm_live import Decoder
        d = Decoder(); d.feed(open(p, 'rb').read()); s = d.split()
        if s is None: sys.exit('not enough data in the file')
        return np.asarray(s[3], float)                       # TIA1-3 raw counts, 50 Hz (signed)
    import pandas as pd
    df = pd.read_csv(p, index_col=False); return (lambda v: np.where(v >= 2 ** 23, v - 2 ** 24, v))(df['TIA1-3_RAW_Value'].dropna().values.astype(float))

def analyze(x):
    out = dict(dur=len(x) / RS.FS)
    # breathing rate every 8 s on 64 s windows
    rate = []
    W = RS.WIN * RS.FS
    for e in range(W, len(x) + 1, 8 * RS.FS):
        r, info = RS.breathing_rate(x[e - W:e]); rate.append([round(e / RS.FS, 1), None if r is None else round(r, 1)])
    out['rate'] = rate
    # pause candidates and waveform over the whole session in 20 min blocks with 2 min overlap (keeps the baseline valid)
    wave = []; pauses = []; blk = 20 * 60 * RS.FS; ov = 120 * RS.FS; s = 0
    while s < len(x):
        seg = x[s:s + blk + ov]; off = s / RS.FS; res = RS.beats_and_series(seg) if len(seg) > 90 * RS.FS else None
        if res is not None:
            t, ser, good = res; tg, w, env, base = RS.breath_wave(t, ser['iv']); sc = 3 * (np.median(env) + 1e-9)
            lim = off + blk / RS.FS if s + blk < len(x) else 1e12
            for a, b in zip(tg, np.clip(w / sc, -1.2, 1.2)):
                if off + a < lim and (not wave or off + a > wave[-1][0]): wave.append([round(off + float(a), 2), round(float(b), 2)])
            for a, b in RS.pause_candidates(t, ser['iv']):
                a += off; b += off
                if not any(a <= q[1] + 1 and b >= q[0] - 1 for q in pauses): pauses.append([round(a, 1), round(b, 1)])
        s += blk
    out['wave'] = wave; out['pauses'] = sorted(pauses); return out

PAGE = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NightPulse breathing report</title>
<style>:root{--bg:#0A141D;--panel:#102331;--line:#1B3547;--text:#E6F1F7;--mute:#8CA6B7;--teal:#2DD4BF;--red:#FF5D6C;--amber:#F5B13D}body{margin:0;background:var(--bg);color:var(--text);font:15px system-ui,sans-serif;padding:16px;max-width:1200px;margin:auto}
h1{font-size:22px;margin:0}h1 b{color:var(--teal)}.sub{color:var(--mute);font-size:13px;margin:4px 0 14px}.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:12px}
h3{margin:0 0 8px;font-size:12px;letter-spacing:1.4px;text-transform:uppercase;color:var(--mute)}.sc{overflow-x:auto}canvas{display:block}table{border-collapse:collapse;width:100%}td,th{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left}
.big{font-size:30px;font-weight:700}.row{display:flex;gap:12px;flex-wrap:wrap}.row .card{flex:1;min-width:150px}</style></head><body>
<h1>Night<b>Pulse</b> breathing report</h1><div class="sub" id="sub"></div>
<div class="row"><div class="card"><h3>Recording</h3><div class="big" id="dur"></div></div><div class="card"><h3>Median breathing rate</h3><div class="big" id="med"></div></div><div class="card"><h3>Pause candidates</h3><div class="big" id="np" style="color:var(--amber)"></div></div></div>
<div class="card"><h3>Breathing waveform (scroll sideways). Red = pause candidate</h3><div class="sc"><canvas id="w"></canvas></div></div>
<div class="card"><h3>Breathing rate (breaths per minute)</h3><canvas id="r" style="width:100%;height:160px"></canvas></div>
<div class="card"><h3>Pause candidates</h3><table id="t"></table></div>
<div class="sub">Educational research prototype. Not a medical device and not a diagnosis. Experimental: on 30 real sleep-study patients (OSASUD) this detector found only 5 to 13% of labeled apnea events at its default setting, so a missing pause means nothing. Check any pause against notes or an oximeter.</div>
<script>const D=__DATA__,f=s=>Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');
document.getElementById('sub').textContent=D.name;document.getElementById('dur').textContent=f(D.dur);document.getElementById('np').textContent=D.pauses.length;
const rr=D.rate.filter(a=>a[1]!=null).map(a=>a[1]).sort((a,b)=>a-b);document.getElementById('med').textContent=rr.length?rr[rr.length>>1].toFixed(0)+' /min':'--';
document.getElementById('t').innerHTML='<tr><th>#</th><th>Start</th><th>Length</th></tr>'+(D.pauses.map((p,i)=>`<tr><td>${i+1}</td><td>${f(p[0])}</td><td>${Math.round(p[1]-p[0])} s</td></tr>`).join('')||'<tr><td colspan=3>none found</td></tr>');
(function(){const c=document.getElementById('w'),g=c.getContext('2d'),PX=8,W=Math.max(1000,Math.ceil(D.dur*PX/1)),H=220,r=devicePixelRatio||1;c.width=W*r;c.height=H*r;c.style.width=W+'px';c.style.height=H+'px';g.scale(r,r);
g.strokeStyle='#1B3547';g.fillStyle='#8CA6B7';g.font='11px system-ui';g.beginPath();g.moveTo(0,H/2-8);g.lineTo(W,H/2-8);g.stroke();for(let s=0;s<=D.dur;s+=60){g.beginPath();g.moveTo(s*PX,0);g.lineTo(s*PX,H-18);g.stroke();g.fillText(f(s),s*PX+3,H-4)}
for(const p of D.pauses){g.fillStyle='rgba(255,93,108,.22)';g.fillRect(p[0]*PX,0,(p[1]-p[0])*PX,H-18);g.fillStyle='#FF5D6C';g.fillText(Math.round(p[1]-p[0])+' s',p[0]*PX+4,12)}
g.strokeStyle='#2DD4BF';g.lineWidth=1.6;g.beginPath();D.wave.forEach((p,i)=>{const x=p[0]*PX,y=(H-18)/2-p[1]*((H-18)/2-8);i&&D.wave[i-1][0]>p[0]-.3?g.lineTo(x,y):g.moveTo(x,y)});g.stroke()})();
(function(){const c=document.getElementById('r'),g=c.getContext('2d'),r=devicePixelRatio||1,W=c.clientWidth,H=c.clientHeight;c.width=W*r;c.height=H*r;g.scale(r,r);g.strokeStyle='#1B3547';g.fillStyle='#8CA6B7';g.font='11px system-ui';
for(const v of[0,10,20,30]){const y=H-16-v/35*(H-24);g.beginPath();g.moveTo(26,y);g.lineTo(W,y);g.stroke();g.fillText(v,2,y+4)}
g.strokeStyle='#2DD4BF';g.lineWidth=2;g.beginPath();let st=1;D.rate.forEach(a=>{if(a[1]==null){st=1;return}const x=26+a[0]/D.dur*(W-26),y=H-16-a[1]/35*(H-24);st?g.moveTo(x,y):g.lineTo(x,y);st=0});g.stroke()})();
</script></body></html>'''

def write_report(x, name, outdir='.'):
    """Analyze PPG samples x (50 Hz) and write <name>_report.html and <name>_pauses.csv into outdir. Returns the result dict."""
    res = analyze(x); res['name'] = name; os.makedirs(outdir, exist_ok=True)
    open(os.path.join(outdir, name + '_report.html'), 'w').write(PAGE.replace('__DATA__', json.dumps(res)))
    with open(os.path.join(outdir, name + '_pauses.csv'), 'w') as f:
        f.write('start_s,end_s,length_s\n'); [f.write(f'{a},{b},{round(b - a, 1)}\n') for a, b in res['pauses']]
    return res

if __name__ == '__main__':
    p = sys.argv[1]; x = load_ppg(p)
    if len(x) < 90 * RS.FS: sys.exit('need at least 90 s of PPG')
    name = os.path.basename(p).rsplit('.', 1)[0]; res = write_report(x, name)
    print(f"{res['dur'] / 60:.1f} min of PPG, {len(res['pauses'])} pause candidates ->", name + '_report.html')
    for a, b in res['pauses']: print(f'  pause candidate {int(a // 60)}:{int(a % 60):02d} for {b - a:.0f} s')
