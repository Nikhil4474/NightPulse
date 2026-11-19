# External and secondary experiments

Run every script from the repository root. Datasets are expected under `work/` (not committed):

| Folder | Content | Source |
|---|---|---|
| `work/osasud/` | OSASUD recordings (30 stroke-unit patients) | Bernardini et al., Scientific Data 2022, figshare (CC0), doi:10.1038/s41597-022-01272-y |
| `work/bidmc/` | BIDMC PPG and Respiration CSV files | PhysioNet, Pimentel et al. 2017 |

Scripts: `osasud_extract.py`, `osasud_safe.py` (safe loader), `osasud_ecg.py` (ECG model on OSASUD), `osasud_ppg.py` (PPG features), `osasud_minutes.py`, `osasud_fuse.py` (ECG plus PPG fusion), `pause_eval.py` and `pause_osasud.py` (breathing pause detector), `resp_cache.py` and `resp_validate.py` (BIDMC breathing rate), `sim_eval.py` (simulator check).
Results are summarized in `docs/VALIDATION.md` and in the report, Section 4.4.
