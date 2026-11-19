# Offline benchmark for the board. Usage: python3 offline_bench.py data/a01 [minutes=60] [runs=5]
# Works with Ethernet connected (SSH stays up): the benchmark runs inside an isolated network
# namespace (unshare -n) that has no network at all, and proves it with a connection test.
# Writes bench_report.json.
import sys, os, json, time, socket, subprocess, platform, statistics, resource
rec = sys.argv[1]; mins = sys.argv[2] if len(sys.argv) > 2 else '60'; runs = int(sys.argv[3]) if len(sys.argv) > 3 else 5

def online():
    try: socket.create_connection(('1.1.1.1', 53), timeout=2).close(); return True
    except Exception: return False

import numpy, scipy, wfdb
import shutil
ISO = ['unshare', '-n'] if shutil.which('unshare') and subprocess.run(['unshare', '-n', 'true']).returncode == 0 else []
def online_isolated():
    code = "import socket\ntry: socket.create_connection(('1.1.1.1',53),timeout=2).close(); print(1)\nexcept Exception: print(0)"
    return subprocess.run(ISO + [sys.executable, '-c', code], capture_output=True, text=True).stdout.strip() == '1'
rep = dict(board=platform.platform(), machine=platform.machine(), python=platform.python_version(),
           numpy=numpy.__version__, scipy=scipy.__version__, wfdb=wfdb.__version__,
           internet_reachable_normal_shell=online(), network_isolated=bool(ISO), internet_reachable_in_benchmark=online_isolated(), record=rec, minutes=int(mins), runs=runs)
try: rep['device_tree_model'] = open('/proc/device-tree/model').read().strip('\0')
except Exception: pass
print('benchmark network isolated:', bool(ISO), '| internet reachable inside benchmark:', rep['internet_reachable_in_benchmark'], '(must be False)')
if not ISO: print('WARNING: unshare missing; unplug Ethernet for a valid offline test')

walls, rsss, per_min = [], [], []
for i in range(runs):
    t = time.perf_counter()
    p = subprocess.Popen(ISO + [sys.executable, 'nightpulse.py', rec, mins], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    so = p.stdout.read(); p.stderr.read()
    _, _, ru = os.wait4(p.pid, 0); p.returncode = 0
    w = time.perf_counter() - t; walls.append(w); rsss.append(ru.ru_maxrss / 1024)  # same value as /usr/bin/time -v
    class out: stdout = so
    for ln in out.stdout.splitlines():
        if ln.startswith('per-minute scoring latency'):
            per_min.append((float(ln.split('mean')[1].split('ms')[0]), float(ln.split('max')[1].split('ms')[0])))
    print(f'run {i+1}/{runs}: {w:.1f} s, peak {rsss[-1]:.0f} MB')
rep['whole_run_seconds'] = dict(median=statistics.median(walls), worst=max(walls), best=min(walls))
rep['peak_memory_mb'] = dict(median=statistics.median(rsss), worst=max(rsss)) if rsss else None
if per_min:
    rep['per_minute_latency_ms'] = dict(median_of_means=statistics.median(m for m, _ in per_min), worst_case=max(x for _, x in per_min))
rep['model_size_bytes'] = os.path.getsize('model.json')
json.dump(rep, open('bench_report.json', 'w'), indent=1)
print(json.dumps(rep, indent=1))
