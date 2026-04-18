# Public EEG Fixtures

This directory is for small public EEG fixtures downloaded locally for broader
cross-dataset validation.

These files are intentionally not committed to git. Use:

```bash
/home/administrator/.local/bin/poetry run python scripts/dev/fetch_public_eeg_fixtures.py
```

Current fixture set:

- `physionet-eegmmidb-S008R01.edf`
  - Source: PhysioNet EEG Motor Movement/Imagery Dataset
  - Format: EDF
  - Type: 64-channel motor imagery EEG
- `bbci-competition-iii-O3VR.gdf`
  - Source: BBCI / BCI Competition III data set IIIb
  - Format: GDF
  - Type: motor imagery with non-stationarity problem
- `sccn-eeglab_data.set`
  - Source: SCCN / EEGLAB tutorial dataset
  - Format: EEGLAB `.set`
  - Type: tutorial EEG sample distributed with EEGLAB

Why these are local-only:

- they broaden real-data coverage beyond the in-repo Graz GDF fixtures
- they come from different public sources, formats, and task types
- keeping them out of git avoids unnecessary repo growth and redistribution ambiguity
