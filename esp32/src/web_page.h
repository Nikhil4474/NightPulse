#pragma once
static const char PAGE[] PROGMEM = R"HTML(<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NightPulse</title>
<style>
:root{--bg:#0A141D;--panel:#102331;--line:#1B3547;--text:#E6F1F7;--mute:#8CA6B7;--teal:#2DD4BF;--green:#4ADE80;--amber:#F5B13D;--red:#FF5D6C}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px system-ui,sans-serif;padding:14px;max-width:980px;margin:auto}
h1{font-size:22px;margin:0 0 2px}h1 b{color:var(--teal)}.sub{color:var(--mute);font-size:13px;margin-bottom:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:12px}
h3{margin:0 0 8px;font-size:12px;letter-spacing:1.4px;text-transform:uppercase;color:var(--mute)}
canvas{width:100%;height:220px;display:block}.row{display:flex;gap:12px;flex-wrap:wrap}.row>.card{flex:1;min-width:140px}
.big{font-size:40px;font-weight:700;line-height:1}.u{color:var(--mute);font-size:14px;margin-left:4px}
button,label.b{background:var(--panel);color:var(--text);border:1px solid var(--line);padding:9px 14px;border-radius:9px;font-size:14px;cursor:pointer;margin-right:8px}
button:hover,label.b:hover{border-color:var(--teal)}.bar{height:8px;background:#0B1B27;border-radius:5px;overflow:hidden;margin-top:8px}.bar i{display:block;height:100%;background:var(--teal);width:0}
.leg{font-size:12px;color:var(--mute)}.leg i{display:inline-block;width:10px;height:10px;border-radius:3px;margin:0 4px 0 10px}
</style></head><body>
<h1>Night<b>Pulse</b></h1><div class="sub">Sleep-apnea research cue running on the ESP32-S3 &middot; offline, no cloud</div>
<div class="row"><div class="card"><h3>Latest risk</h3><div><span class="big" id="sc">--</span></div><div class="u" id="vd" style="margin:6px 0 0">waiting for data</div></div>
<div class="card"><h3>Heart rate</h3><span class="big" id="hr">--</span><span class="u">beats/min</span></div>
<div class="card"><h3>Minutes</h3><div>scored <b id="ns">0</b> &middot; apnea-like <b id="na" style="color:var(--red)">0</b> &middot; unknown <b id="nu" style="color:var(--amber)">0</b></div><div class="u" id="st" style="margin:6px 0 0">idle</div><div class="bar"><i id="pg"></i></div></div></div>
<div class="card"><h3>Apnea-like risk, one bar per minute</h3><canvas id="cv"></canvas>
<div class="leg"><i style="background:var(--green)"></i>normal<i style="background:var(--amber)"></i>borderline<i style="background:var(--red)"></i>apnea-like<i style="background:#3A4F5F"></i>unknown</div></div>
<div class="card"><h3>Data</h3><label class="b">Upload beat log<input id="f" type="file" accept=".csv,.txt,.rr" hidden></label><button id="demo">Run demo</button><button id="clr">Clear</button>
<div class="u" style="margin-top:10px">Beat log: one beat time in milliseconds per line (the file the ESP32 or the SK-AM62B dashboard saves). Needs at least 5 minutes. A score appears about 3 minutes after each minute it describes.</div></div>
<div class="sub">Educational research prototype. Not a medical device and not a diagnosis. Scores come from a model trained on PhysioNet Apnea-ECG and flag about 1 in 5 normal minutes.</div>
<script>
const $=i=>document.getElementById(i),cv=$('cv'),g=cv.getContext('2d');
function col(s){return s==null?'#3A4F5F':s>.5?'#FF5D6C':s>=.4?'#F5B13D':'#4ADE80'}
function draw(h){const r=devicePixelRatio||1,W=cv.clientWidth,H=cv.clientHeight;cv.width=W*r;cv.height=H*r;g.setTransform(r,0,0,r,0,0);g.clearRect(0,0,W,H);
const L=28,B=H-18,T=6,P=H-18-T;g.strokeStyle='#1B3547';g.fillStyle='#8CA6B7';g.font='11px system-ui';for(const v of[0,.5,1]){const y=B-v*P;g.beginPath();g.moveTo(L,y);g.lineTo(W,y);g.setLineDash(v==.5?[5,4]:[]);g.stroke();g.fillText(v,2,y+4)}g.setLineDash([]);
const n=h.length;if(!n)return;const bw=Math.max(1,Math.min(8,(W-L)/n));for(let i=0;i<n;i++){const s=h[i][0]<0?null:h[i][0]/100;g.fillStyle=col(s);const x=L+i*(W-L)/Math.max(n,(W-L)/8);const hh=s==null?10:Math.max(2,s*P);g.fillRect(x,B-hh,Math.max(1,bw-.5),hh)}
g.fillStyle='#8CA6B7';g.fillText('minute 2',L,H-4);g.fillText('minute '+(n+1),W-62,H-4)}
async function tick(){try{const d=await (await fetch('/api/state')).json(),h=d.h;draw(h);$('st').textContent=d.status+(d.status==='idle'?'':' '+d.pct+'%');$('pg').style.width=d.pct+'%';
let ok=h.filter(x=>x[0]>=0),last=ok.length?ok[ok.length-1]:null;$('sc').textContent=last?(last[0]/100).toFixed(2):'--';$('sc').style.color=last?col(last[0]/100):'';$('vd').textContent=last?(last[0]>50?'APNEA-LIKE':last[0]>=40?'borderline':'normal pattern'):'waiting for data';$('hr').textContent=last?last[1]:'--';
$('ns').textContent=ok.length;$('na').textContent=ok.filter(x=>x[0]>50).length;$('nu').textContent=h.length-ok.length}catch(e){}}
setInterval(tick,1500);tick();addEventListener('resize',tick);
$('demo').onclick=()=>fetch('/api/demo');$('clr').onclick=()=>fetch('/api/clear');
$('f').onchange=async e=>{const f=e.target.files[0];if(!f)return;const fd=new FormData();fd.append('f',f,'beats.csv');$('st').textContent='uploading';await fetch('/api/upload',{method:'POST',body:fd});e.target.value=''};
</script></body></html>)HTML";
