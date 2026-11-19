# NightPulse data sources (model nightpulse-lr-v4)

| Dataset | Named in Track 2 manual | Use | Size used |
|---|---|---|---|
| PhysioNet Apnea-ECG | Not by name. Falls under "PhysioNet Physiological Databases" (manual section 5). The only source with apnea labels. | Training and validation (apnea vs normal minutes) | 35 records, 15,790 usable minutes |
| WESAD | Yes | Training: awake healthy examples labelled non-apnea (assumption: not screened for apnea) | 15 subjects, 1,348 usable minutes |
| MIT-BIH Arrhythmia | Yes | Gate test only (quality gate and out-of-range guard); no apnea labels | 48 records, 1,440 minutes |
| BIDMC PPG and Respiration | Yes | Breathing-rate check for the experimental PPG branch (held-out even-numbered records) | 1,357 windows |
| PhysioNet Apnea-ECG test set x01-x35 | Not by name | Final held-out test of the deployed pipeline, never trained on | 35 records, 17,073 minutes |
| OSASUD (Bernardini et al., Sci Data 2022, figshare, CC0) | No | External test on a different population | 30 patients, 267 hours |

Not used for training: live EVM recordings (your own captures), including the friend's session and the simulator capture.
Subject or record level cross-validation. Numbers are in model_card.json.
