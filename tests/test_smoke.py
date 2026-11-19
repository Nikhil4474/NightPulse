"""Smoke test. Run from the repo root:  python3 tests/test_smoke.py
Checks that the shipped model scores the bundled a01 / c01 records and that the quality gate abstains on bad input."""
import os, sys, subprocess, re, numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); APP = os.path.join(ROOT, 'nightpulse')
def run(rec, mins):
    out = subprocess.run([sys.executable, 'nightpulse.py', rec, str(mins)], cwd=APP, capture_output=True, text=True, check=True).stdout
    n = int(re.search(r'minutes scored: (\d+)', out).group(1)); sc = [float(x) for x in re.findall(r'risk ([0-9.]+)', out)]
    return n, sc
n, a = run('data/a01', 30)
assert n >= 20, 'too few minutes scored'
assert all(0 <= s <= 1 for s in a)
print('a01 (apnea record): %d minutes scored' % n)
n, c = run('data/c01', 30)
assert n >= 20
print('c01: %d minutes scored' % n)
sys.path.insert(0, APP); os.chdir(APP)
import nightpulse as NP
ok, why = NP.quality_ok(np.zeros(6000), np.array([]))
assert not ok, 'flatline must be rejected'
print('flatline rejected:', why)
print('OK')
