"""Download the public PhysioNet datasets used for training and testing (needs internet; ~200 MB for the Apnea-ECG database).
Usage (repo root):  python3 scripts/download_data.py            # Apnea-ECG learning + test records into work/apnea_ecg/
Other datasets (WESAD, MIT-BIH, BIDMC, OSASUD) are described in docs/DATA_SOURCES.md and evaluation/external/README.md.
Apnea-ECG is published under the Open Data Commons Attribution License v1.0 (Penzel et al., Computers in Cardiology 2000)."""
import os, wfdb
out = 'work/apnea_ecg'; os.makedirs(out, exist_ok=True)
wfdb.dl_database('apnea-ecg', out)
print('done ->', out)
