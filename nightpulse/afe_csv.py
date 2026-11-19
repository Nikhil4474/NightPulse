"""Convert a TI AFE4950 GUI export (AFE4950_CAPTURED_DATA.csv) into a 100 Hz recording the NightPulse pipeline and dashboard can use.
Usage: python3 afe_csv.py path/to/AFE4950_CAPTURED_DATA.csv  [name]      -> writes data/<name>.dat/.hea
Columns used (per TI export / Track 1 manual): ECG_Time, ECG_Value (about 500 Hz). Trailing delimiter handled with index_col=False."""
import sys, os, numpy as np, pandas as pd, wfdb
from scipy.signal import decimate, detrend, butter, sosfiltfilt, iirnotch, filtfilt
src = sys.argv[1]; name = sys.argv[2] if len(sys.argv) > 2 else 'afe_capture'
df = pd.read_csv(src, index_col=False)
e = df[['ECG_Time', 'ECG_Value']].dropna()
t = e['ECG_Time'].to_numpy(float); x = e['ECG_Value'].to_numpy(float)
span = t[-1] - t[0]
# time unit guess: pick the scale that makes the sample rate closest to the documented 500 Hz
fs_guess = {s: (len(t) - 1) / (span * s) for s in (1.0, 1e-3, 1e-6)}
scale = min(fs_guess, key=lambda s: abs(fs_guess[s] - 500)); fs = fs_guess[scale]
print(f'{len(t)} ECG samples, {span*scale:.1f} s, estimated rate {fs:.0f} Hz (time unit x{scale})')
# uniform resample to 500 Hz, anti-alias decimate by 5 to 100 Hz
tu = np.arange(t[0], t[-1], 1/500/scale); xu = np.interp(tu, t, x)
xu = detrend(xu, type='constant')
# documented preprocessing: 60 Hz notch (mains) then 0.5-35 Hz band-pass, zero phase
# mains pickup shows at 60 Hz (measured 60.2 Hz on our EVM) AND as a ~10 Hz image (60.2 minus the 50 Hz frame rate), so notch both
for f0 in (60.0, 60.2, 10.15):
    b, a = iirnotch(f0, 30, 500); xu = filtfilt(b, a, xu)
xu = sosfiltfilt(butter(3, [0.5, 35], btype='band', fs=500, output='sos'), xu)
y = decimate(xu, 5, ftype='fir', zero_phase=True)
y = y / (np.percentile(np.abs(y), 99.5) + 1e-12) * 1.0          # scale so R waves are about 1 mV-like, whatever the ADC units
os.makedirs('data', exist_ok=True)
wfdb.wrsamp(name, fs=100, units=['mV'], sig_name=['ECG'], p_signal=y.reshape(-1, 1), fmt=['16'], write_dir='data')
print(f'wrote data/{name}.dat ({len(y)/100:.1f} s at 100 Hz). Needs at least 5 minutes for the model to score; shorter files can only show the beat detector.')
