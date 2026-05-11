# Public EEG Fixtures

這個資料夾放的是「只在本地下載、不進 git」的公開 EEG fixtures，
用途是補強 repo 內建真實資料之外的跨來源、跨格式驗證。

下載指令：

```bash
/home/administrator/.local/bin/poetry run python scripts/dev/fetch_public_eeg_fixtures.py
```

目前 fixture 組合：

- `physionet-eegmmidb-S008R01.edf`
  - Source: PhysioNet EEG Motor Movement/Imagery Dataset
  - Format: EDF
  - Type: baseline / rest-style EDF import coverage
- `physionet-eegmmidb-S008R04.edf`
  - Source: PhysioNet EEG Motor Movement/Imagery Dataset
  - Format: EDF
  - Type: event-rich motor imagery EDF for one-epoch smoke
- `bbci-competition-iii-O3VR.gdf`
  - Source: BBCI / BCI Competition III data set IIIb
  - Format: GDF
  - Type: event-rich motor imagery with non-stationarity problem
- `sccn-eeglab_data.set`
  - Source: SCCN / EEGLAB tutorial dataset
  - Format: EEGLAB `.set`
  - Type: event-rich tutorial EEG sample distributed with EEGLAB
- `scan41_short.cnt`
  - Source: MNE testing-data
  - Format: Neuroscan CNT
  - Type: event-rich compact CNT sample
- `test_NO.vhdr`
  - Source: MNE testing-data
  - Format: BrainVision `.vhdr`
  - Sidecars: `test_NO.eeg`, `test_NO.vmrk`
  - Type: compact BrainVision sample for sidecar-format coverage

目前這組 public baseline 已覆蓋：

- EDF
- GDF
- EEGLAB `.set`
- CNT
- BrainVision `.vhdr`

其中目前可直接推進到 cross-source one-epoch training smoke 的 event-rich fixtures 是：

- `physionet-eegmmidb-S008R04.edf`
- `bbci-competition-iii-O3VR.gdf`
- `sccn-eeglab_data.set`
- `scan41_short.cnt`

可重跑命令：

```bash
/home/administrator/.local/bin/poetry run python scripts/dev/run_public_cross_source_training_smoke.py --format markdown
/home/administrator/.local/bin/poetry run python scripts/dev/run_public_cross_source_training_smoke.py --format json --strict
```

目前仍停在 import/facade breadth 的 fixture 是：

- `physionet-eegmmidb-S008R01.edf`
- `test_NO.vhdr`

為什麼保持 local-only：

- 它們能補足 repo 內 checked-in fixtures 沒有涵蓋到的資料來源多樣性
- 它們能補強 public-source format coverage，而不讓 repo 持續膨脹
- 某些來源的再散布邊界不如 repo 內自製 compact fixtures 那麼單純
