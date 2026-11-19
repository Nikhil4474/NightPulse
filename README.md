# NightPulse

Offline sleep-apnea **risk cue** from a three-lead ECG (red, black, white electrodes), built for UTiD HackEdge 2026, Track 2 (Intelligent Physiological Analytics) by Team Matrix Bros, UT Dallas.
It runs on the TI **SK-AM62B** board with a TI **AFE4950EVM** sensor, and there is a port to an **ESP32-S3**.

> **Research prototype, not a medical device.** NightPulse gives a heartbeat-timing risk cue. It does not diagnose sleep apnea.

Final report: see the PDF/Word file submitted to the HackEdge Box folder (it links back to this repository).

## What it does

1. Reads ECG (500 Hz) and optical pulse (50 Hz) from the AFE4950EVM, or replays a public recording.
2. Resamples ECG to 100 Hz, band-pass filters 0.5 to 35 Hz, finds heartbeats (WFDB XQRS).
3. Quality gate per minute (flatline, clipping, beat count, irregular beats). Bad minutes are reported as `UNKNOWN`.
4. 29 heartbeat-timing features per minute, scored by a logistic regression (`nightpulse/model.json`, 3.7 KB).
5. Out-of-range guard: if 6 or more features are outside the training range, the minute is also `UNKNOWN`.
6. A local web dashboard (no internet needed) shows the live ECG, risk gauge and history, and exports a session bundle.

Measured results (details and caveats in the report and in `docs/VALIDATION.md`):

| Test | Result |
|---|---|
| Held-out PhysioNet Apnea-ECG test records x01-x35 (17,073 minutes, 7.6% abstained) | AUROC 0.858 (95% CI 0.784 to 0.921), sensitivity 77.5%, specificity 79.8% at threshold 0.5 |
| 5-fold cross-validation on the learning set | AUROC 0.809 (95% CI 0.72 to 0.881) |
| OSASUD stroke-unit patients (different population) | AUROC 0.564, did not transfer |
| SK-AM62B benchmark, network isolated, 63 min of ECG | 26 s whole run, 27.6 ms per minute of ECG, 175 MB peak memory (measured with an earlier 2.1 KB model file, see Limitations) |

## Repository layout

```
nightpulse/    on-board application: pipeline, dashboard, EVM capture, model.json, benchmark, bundled sample records
esp32/         ESP32-S3 firmware (C++ port of the same model), PlatformIO project
training/      feature extraction and model training (reproduces model.json exactly)
evaluation/    held-out test scripts and external experiments (OSASUD, BIDMC)
docs/          model card, validation summary, data sources, report figures, board benchmark sheet
scripts/       dataset download helper
tests/         smoke test
```

## Installation and dependencies

Python 3.10 or newer (tested with 3.13 on a laptop and 3.14 on the SK-AM62B), on Linux, macOS or Windows.

```bash
git clone <this repository>
cd NightPulse
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Core runtime needs only `numpy`, `scipy` and `wfdb`. `scikit-learn`, `pandas` and `matplotlib` are needed only for training, evaluation and figures.
Live capture from the AFE4950EVM (`evm_live.py`) uses `termios` and works on Linux only (the SK-AM62B).

## Quick start (replay, no hardware)

```bash
python3 tests/test_smoke.py                      # should end with: OK
cd nightpulse
python3 nightpulse.py data/a01 60                # score the first 60 minutes of an apnea record
python3 dashboard.py data/a01 120                # dashboard, then open http://localhost:8000
python3 dashboard.py data/c01 120                # a normal record
```

`data/a01` and `data/c01` are PhysioNet Apnea-ECG records (Open Data Commons Attribution License, Penzel et al. 2000). The dashboard has three modes: REPLAY (this), LIVE_EVM and LIVE_TEST (built-in signal generator).

## Running on the SK-AM62B with the AFE4950EVM

1. Copy the `nightpulse/` folder to the board and `pip install numpy scipy wfdb`.
2. Plug the EVM into a USB port (it appears as `/dev/ttyACM*`). The register files from TI's GUI are in `nightpulse/evm/`.
3. `python3 dashboard.py live --export-dir exports` (optionally `--backup-dir /media/usb/nightpulse` for a second copy of the raw data every 30 s).
4. Open `http://<board-ip>:8000` from a laptop or phone on the same network.
5. Stopping a session writes an export bundle (raw capture, TI-style CSV, 100 Hz record, `minute_scores.csv`, `report.html`, `summary.json`, zip).
6. Optional: `HOTSPOT_SSID=... HOTSPOT_PASS=... sh hotspot_connect.sh` keeps the board joined to a phone hotspot (add `install` to run at boot). Nothing is sent to the internet.

Other tools: `evm_probe.py` (check the EVM link), `afe_csv.py` (convert a TI GUI CSV to a 100 Hz record), `analyze_session.py` (score a saved session).

## Benchmark on the board

```bash
cd nightpulse
python3 offline_bench.py data/a01 60 5      # 5 runs of 60 minutes inside an isolated network namespace (unshare -n)
```

It writes `bench_report.json` with run time, peak memory, per-minute latency, model file size and a proof that the network was unreachable.

## ESP32-S3 port

See `esp32/README.md`. In short: install PlatformIO, then `cd esp32 && pio run -e s3_lcd147 -t upload`. The chip creates its own WiFi network `NightPulse` and serves a dashboard at `http://192.168.4.1`. `esp32/tools/host_test.cpp` checks the C++ core against the Python scores (max difference 4.7e-6). ESP32 latency and memory have not been measured.

## Reproducing the model and the results

Download the public data (about 200 MB for Apnea-ECG, needs internet):

```bash
python3 scripts/download_data.py            # fills work/apnea_ecg/
```

Retrain the shipped model from the stored feature matrices (checks that every constant matches `nightpulse/model.json`):

```bash
python3 training/train_v4.py
```

Rebuild the feature matrices from raw records: `training/extract_beats.py` (XQRS beats), `training/extract_features_cv.py` (features and 5-fold cross-validation, run inside the folder holding the records), `training/wesad_extract.py` and `training/wesad_feats.py` (WESAD, needs the WESAD download).

Re-run the held-out test of the deployed pipeline on the 35 test records:

```bash
python3 evaluation/heldout_run.py work/apnea_ecg work/xeval
python3 evaluation/heldout_metrics.py work/xeval
```

External experiments (OSASUD, BIDMC breathing rate) are listed in `evaluation/external/README.md`.

## Limitations

* Accuracy is only reported on public datasets. No accuracy is claimed from AFE4950EVM recordings, and a full live session on the board (EVM to score) was not demonstrated in time for the final round.
* The 2,127-byte model file in the board benchmark was an earlier build. The final `model.json` is 3,703 bytes (it adds the clipping and out-of-range limits). Re-run `offline_bench.py` to refresh the numbers.
* The model did not transfer to stroke-unit patients (OSASUD, AUROC 0.56). The PPG breathing branch is experimental and does not feed the score.
* WESAD minutes are used as non-apnea examples without apnea screening.
* The score needs 2 minutes of future data, so it lags by about 3 minutes.

## Data and citations

See `docs/DATA_SOURCES.md` and the reference list of the report. Main sources: PhysioNet Apnea-ECG (Penzel et al. 2000), WESAD (Schmidt et al. 2018), MIT-BIH Arrhythmia (Moody and Mark 2001), BIDMC (Pimentel et al. 2017), OSASUD (Bernardini et al. 2022), WFDB-Python.

## License

MIT, see `LICENSE`. Datasets keep their own licenses.
