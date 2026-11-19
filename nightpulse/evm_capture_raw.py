# Raw capture from the AFE4950EVM CAPTURE port. Saves every 4-byte word to a CSV for decoding.
# Usage: python3 evm_capture_raw.py [seconds=10]
# It does NOT load any AFE settings: the chip must already be configured (by TI's GUI, or a config we replay later).
import sys, os, glob, time, select, csv
from evm_probe import open_port, ask, quiet
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 10
cap = None
for p in sorted(glob.glob('/dev/ttyACM*')):
    fd = open_port(p); quiet(fd)
    if b'CAPTURE' in ask(fd, 'C:CDC?', 1.0): cap = (p, fd); break
    os.close(fd)
if not cap: sys.exit('capture port not found')
p, fd = cap; print('capture port:', p)
termios_flush = __import__('termios').tcflush; termios_flush(fd, __import__('termios').TCIOFLUSH)
os.write(fd, b'C:CAP_START' + b'00' + b'00000000')      # continuous capture
buf = b''; t0 = time.time()
while time.time() - t0 < secs:
    if select.select([fd], [], [], 0.2)[0]:
        try: buf += os.read(fd, 65536)
        except BlockingIOError: pass
os.write(fd, b'C:CAP_STOP'); time.sleep(0.3)
try: buf += os.read(fd, 65536)
except BlockingIOError: pass
os.close(fd)
n = len(buf) // 4; words = [(buf[4*i] | buf[4*i+1] << 8 | buf[4*i+2] << 16, buf[4*i+3]) for i in range(n)]
with open('raw_capture.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['index', 'value24', 'id']); [w.writerow([i, v, k]) for i, (v, k) in enumerate(words)]
ids = {}
for v, k in words: ids[k] = ids.get(k, 0) + 1
print(f'{len(buf)} bytes, {n} words in {secs:.0f} s; word ids (3=fifo level, 5=fifo data, 2/0/1/7=headers/extra): {ids}')
print('first data words:', [v for v, k in words if k == 5][:12])
