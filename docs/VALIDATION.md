# NightPulse validation summary (measured)
| Test | Data | Result |
|---|---|---|
| ECG model, held-out test | PhysioNet Apnea-ECG x01-x35 (35 records, 15,780 minutes, never trained on) | AUROC 0.858 (95% CI 0.784-0.921), sensitivity 77.5%, specificity 79.8% at 0.5, 7.6% abstained. Record level apnea vs normal AUROC 0.91 |
| ECG model, other population | OSASUD, 30 stroke-unit patients, 267 h, 80 Hz monitor ECG, labels include hypopnea | AUROC 0.564 (barely above chance), 19% abstained. Did not transfer |
| PPG breathing pause detector (default settings) | OSASUD finger PPG, 1,205 + 1,841 labeled apnea events | detected 5% (dev half) and 13% (test half) of apnea events, 2.4-2.8 false alarms per hour |
| Same detector, retuned on dev half | OSASUD, held-out even patients | about 57% of apnea events at about 24 false alarms per hour, precision 0.39. Not deployed |
| Learned PPG features (breathing, pulse amplitude, pulse-rate variability), leave-one-patient-out | OSASUD minutes | AUROC 0.62 (logistic) to 0.68 (boosted trees); adding the ECG score gave no gain (0.673) |
Conclusions: the ECG model works on the PhysioNet population it was built for but did not carry over to hospital patients. PPG breathing features carry a little signal but are not accurate enough to confirm or rule out apnea, and did not strengthen the ECG result here. Do not claim apnea detection or diagnosis. Datasets: PhysioNet Apnea-ECG; OSASUD (Bernardini et al. 2022, figshare, CC0).
