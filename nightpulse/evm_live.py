"""Live capture from the AFE4950EVM straight into the board (no Windows PC).
Usage:  python3 evm_live.py <minutes> <name> [--cfg evm/AFE4950_Settings.cfg] [--no-config]
Steps: reset AFE, write the TI register settings (.cfg), read back a few registers, start capture, decode the FIFO
(11-word frame: ECG x6, TIA1-3 x1, ECG x4 = 500 Hz ECG + 50 Hz optical), save a TI-style CSV and a 100 Hz recording
data/<name> that the dashboard can play. Protocol from TI's AFE4950 EVM firmware source (pcComm.c).
Scale: 24-bit signed counts * 1.2 V / 2^21 = 5.722e-7 V per count (fitted on TI's own CSV export, exact)."""
import sys, os, glob, time, select, termios, re, csv, argparse
import numpy as np
from evm_probe import open_port, ask, quiet

V = 1.2 / 2**21; FRAME = ['ECG']*6 + ['TIA'] + ['ECG']*4

def find_ports():
    reg = cap = None
    for p in sorted(glob.glob('/dev/ttyACM*')):
        fd = open_port(p); quiet(fd); r = ask(fd, 'C:CDC?', 1.0)
        if b'REG_EDIT' in r: reg = fd
        elif b'CAPTURE' in r: cap = fd
        else: os.close(fd)
    if reg is None or cap is None: sys.exit('EVM ports not found: check the USB cable and run evm_probe.py')
    return reg, cap

def parse_cfg(path):
    out = []
    for ln in open(path):
        m = re.match(r'\s*(AFE4950(?:_PPM)?)\|0x([0-9A-Fa-f]+)\s+0x([0-9A-Fa-f]+)', ln)
        if m: out.append((int(m.group(2), 16), int(m.group(3), 16)))
    return out

def reg_write(fd, a, v):
    r = ask(fd, 'C:REG_W%02X%06X1' % (a, v), 0.5, b'\n')
    if b'SUCCESS' not in r: raise RuntimeError(f'write 0x{a:02X} failed: {r!r}')

def reg_read(fd, a):
    r = ask(fd, 'C:REG_R%02X1' % a, 0.5, b'\n')
    return int(r.split(b'\n')[1], 16) if b'SUCCESS' in r else None

def s24(v): return v - (1 << 24) if v >= (1 << 23) else v

class Decoder:
    """4-byte words: 3 data bytes (LSB first) + id. id 2 = packet start, id 3 = FIFO level L, then (L+1)&0xFF data words of id 5."""
    def __init__(self, offset=None): self.buf = b''; self.left = 0; self.words = []; self.offset = offset; self.bad = 0
    def feed(self, data):
        self.buf += data; n = len(self.buf) // 4
        for i in range(n):
            b = self.buf[4*i:4*i+4]; v = b[0] | b[1] << 8 | b[2] << 16; k = b[3]
            if k == 5: self.words.append(s24(v))
            elif k == 3: self.left = ((v + 1) & 0xFF)
            elif k not in (2, 1, 7): self.bad += 1
        self.buf = self.buf[4*n:]
    def split(self):
        w = np.array(self.words, dtype=float); off = self.offset
        if off is None:   # TIA slot = the one whose values are far from the ECG slots (ECG is near zero)
            n = (len(w) // 11) * 11
            if n < 110: return None
            med = np.median(np.abs(w[:n].reshape(-1, 11)), axis=0); off = (6 - int(np.argmax(med))) % 11
            self.offset = off
        w = w[off:]; n = (len(w) // 11) * 11; f = w[:n].reshape(-1, 11)
        tia = f[:, 6]; ecg = np.delete(f, 6, axis=1).reshape(-1)
        return ecg * V, tia * V, ecg, tia

def save(name, ecg_v, tia_v, ecg_r, tia_r):
    os.makedirs('data', exist_ok=True); path = f'data/{name}_AFE4950_CAPTURED_DATA.csv'
    with open(path, 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['ECG_Time', 'ECG_Value', 'ECG_RAW_Time', 'ECG_RAW_Value', 'TIA1-3_Time', 'TIA1-3_Value', 'TIA1-3_RAW_Time', 'TIA1-3_RAW_Value'])
        for i in range(len(ecg_v)):
            row = [i/500, ecg_v[i], i/500, int(ecg_r[i]) & 0xFFFFFF]
            row += [i/50, tia_v[i], i/50, int(tia_r[i]) & 0xFFFFFF] if i < len(tia_v) else ['', '', '', '']
            w.writerow(row)
    return path


import threading
from scipy.signal import iirnotch, butter, tf2sos, sosfilt, sosfilt_zi

class EvmStream:
    """Background EVM reader for the dashboard: configure the chip, capture, decode, and hand out filtered 100 Hz ECG on request."""
    def __init__(self, cfg='evm/AFE4950_Settings.cfg', configure=True, offset=None):
        self.cfg, self.configure, self.dec = cfg, configure, Decoder(offset)
        self.lock = threading.Lock(); self.stop_flag = False; self.state = 'starting'; self.msg = ''; self.err = None
        self.wpos = None; self.backup = None; self._tia_new = []; self.ecg_raw = []; self.tia_raw = []; self.pending = []; self.scale = None; self.zi = None; self.n500 = 0
        b, a = iirnotch(60, 30, 500)
        self.sos = np.vstack([tf2sos(b, a), butter(4, [0.5, 35], btype='band', fs=500, output='sos')])
        self.thread = threading.Thread(target=self._run, daemon=True); self.thread.start()
    def _run(self):
        reg = cap = None
        try:
            reg, cap = find_ports()
            if self.configure:
                self.state = 'configuring'; cfg = parse_cfg(self.cfg); ask(reg, 'C:RST_AFE', 0.5); time.sleep(0.2)
                for i, (ad, v) in enumerate(cfg):
                    reg_write(reg, ad, v)
                    if i % 20 == 0: self.msg = f'loading chip settings {i}/{len(cfg)}'
                reg_write(reg, 0x01, 0); time.sleep(0.2)
            termios.tcflush(cap, termios.TCIOFLUSH); os.write(cap, b'C:CAP_START' + b'00' + b'00000000')
            self.state = 'running'; self.msg = 'capturing'
            os.makedirs('data', exist_ok=True); self.rawpath = 'data/live_' + time.strftime('%Y%m%d_%H%M%S') + '.raw'; rawf = open(self.rawpath, 'ab')
            lastsync = lastbak = time.time()
            while not self.stop_flag:
                if time.time() - lastsync > 5:    # push the raw file through to the SD card every 5 s, and to the backup folder every 30 s
                    try: os.fsync(rawf.fileno())
                    except OSError: pass
                    if self.backup and time.time() - lastbak > 30:
                        try: import shutil; os.makedirs(self.backup, exist_ok=True); shutil.copyfile(self.rawpath, os.path.join(self.backup, os.path.basename(self.rawpath)))
                        except Exception as ex: self.msg = 'backup failed: ' + str(ex)
                        lastbak = time.time()
                    lastsync = time.time()
                if select.select([cap], [], [], 0.2)[0]:
                    try: data = os.read(cap, 65536)
                    except BlockingIOError: continue
                    rawf.write(data); rawf.flush()   # lossless autosave: survives Ctrl+C or a crash
                    with self.lock: self.dec.feed(data)
            os.write(cap, b'C:CAP_STOP'); time.sleep(0.3); rawf.close()
        except (Exception, SystemExit) as e: self.err = str(e) or 'EVM error'; self.state = 'error'
        finally:
            for fd in (reg, cap):
                try: os.close(fd)
                except Exception: pass
            if self.state != 'error': self.state = 'stopped'
    def stop(self): self.stop_flag = True
    def pull100(self):
        """New filtered ECG samples at 100 Hz (np array, possibly empty)."""
        with self.lock:
            w = self.dec.words
            if self.wpos is None:
                if len(w) < 330: return np.zeros(0)
                if self.dec.offset is None:
                    med = np.median(np.abs(np.array(w[:330], float)).reshape(-1, 11), axis=0); self.dec.offset = (6 - int(np.argmax(med))) % 11
                self.wpos = self.dec.offset
            nf = (len(w) - self.wpos) // 11
            if nf == 0: return np.zeros(0)
            f = np.array(w[self.wpos:self.wpos + 11 * nf], float).reshape(-1, 11); self.wpos += 11 * nf
        self._tia_new.append(f[:, 6] * V); self.tia_raw.append(f[:, 6].astype(np.int32)); e = np.delete(f, 6, axis=1).reshape(-1); self.ecg_raw.append(e.astype(np.int32))
        x = e * V
        if self.zi is None: self.zi = sosfilt_zi(self.sos)[:, None, :].reshape(-1, 2) * x[0]
        y, self.zi = sosfilt(self.sos, x, zi=self.zi)
        idx = np.arange(self.n500, self.n500 + len(y)); self.n500 += len(y); y = y[idx % 5 == 0]
        if self.scale is None:
            self.pending.append(y); p = np.concatenate(self.pending)
            if len(p) < 1000: return np.zeros(0)
            self.scale = 1.0 / (np.percentile(np.abs(p[200:]), 99.5) + 1e-12); self.pending = []; return p * self.scale
        return y * self.scale
    def take_ppg(self):
        """New optical (TIA1-3) samples at 50 Hz in volts since the last call."""
        out = np.concatenate(self._tia_new) if self._tia_new else np.zeros(0); self._tia_new = []; return out
    def export(self, name):
        if not self.ecg_raw: return None
        er = np.concatenate(self.ecg_raw); tr = np.concatenate(self.tia_raw)
        return save(name, er * V, tr * V, er, tr)

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('minutes', type=float); ap.add_argument('name')
    ap.add_argument('--cfg', default='evm/AFE4950_Settings.cfg'); ap.add_argument('--no-config', action='store_true')
    ap.add_argument('--offset', type=int, default=None); a = ap.parse_args()
    reg, cap = find_ports()
    print('EVM:', ask(reg, 'DEVICE?').strip(), ask(reg, 'FIRMWARE_VER?').strip())
    if not a.no_config:
        cfg = parse_cfg(a.cfg); print(f'loading {len(cfg)} register writes from {a.cfg}')
        ask(reg, 'C:RST_AFE', 0.5); time.sleep(0.2)
        for ad, v in cfg: reg_write(reg, ad, v)
        reg_write(reg, 0x01, 0); time.sleep(0.2)
        want = {ad: v for ad, v in cfg[:89]}; bad = [(hex(k), hex(want[k]), reg_read(reg, k)) for k in (0x1D, 0x42, 0x6C, 0x8A)]
        print('read-back (reg, wanted, got):', bad)
    termios.tcflush(cap, termios.TCIOFLUSH)
    os.write(cap, b'C:CAP_START' + b'00' + b'00000000')
    dec = Decoder(a.offset); t0 = time.time(); last = t0
    try:
        while time.time() - t0 < a.minutes * 60:
            if select.select([cap], [], [], 0.2)[0]:
                try: dec.feed(os.read(cap, 65536))
                except BlockingIOError: pass
            if time.time() - last > 10:
                last = time.time(); el = last - t0
                print(f'{el:5.0f} s  words {len(dec.words)}  ({len(dec.words)/el:.0f}/s, expect 550)')
    except KeyboardInterrupt: pass
    os.write(cap, b'C:CAP_STOP'); time.sleep(0.3)
    el = time.time() - t0; s = dec.split()
    if s is None: sys.exit('not enough data: the chip is probably not sampling (check the config and the ECG input)')
    ecg_v, tia_v, ecg_r, tia_r = s
    print(f'{len(dec.words)} words in {el:.0f} s ({len(dec.words)/el:.0f}/s, expect 550); frame offset {dec.offset}; unknown words {dec.bad}')
    p = save(a.name, ecg_v, tia_v, ecg_r, tia_r); print('saved', p)
    os.system(f'{sys.executable} afe_csv.py {p} {a.name}')
