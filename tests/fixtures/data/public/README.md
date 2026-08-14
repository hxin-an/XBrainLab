# Public EEG Fixtures

這個資料夾是未設定 `XBRAINLAB_DATA_DIR` 時的 repo/CI fallback cache。一般本機可把
`XBRAINLAB_DATA_DIR` 指到 D 槽的 durable data root；下載器會改用
`$XBRAINLAB_DATA_DIR/datasets/public-fixtures/`，用途仍是補強 repo 內建真實資料之外的跨來源、
跨格式驗證。

下載指令：

```bash
/home/administrator/.local/bin/poetry run -- python scripts/dev/fetch_public_eeg_fixtures.py
```

下載器會驗證公開檔案的 SHA-256，避免 0-byte 或 partial download 被誤當成可用 fixture。
每個檔案也有固定 byte size；下載先寫入 `.part`，只有 size 與 SHA-256 都正確才會
原子替換既有 cache，失敗下載不會破壞上一份有效 fixture。

Required CI 使用受控的小型 profile：

```bash
poetry run -- python scripts/dev/fetch_public_eeg_fixtures.py --profile required-ci
poetry run -- python scripts/dev/fetch_public_eeg_fixtures.py \
  --profile required-ci --verify-only
```

- manifest 目前總量是 `205,255,918 bytes`，程式內硬上限為 `220 MiB`
- CI fixture 存在 `tests/fixtures/data/public/`；設定 data root 的本機 fixture 存在 canonical
  `datasets/public-fixtures/`。兩者都不進 Git
- GitHub Actions 只 cache 這個目錄；cache key 綁定下載器 manifest 的 hash
- cache 過期或內容損壞時，下載器會逐檔驗證並修復；`--verify-only` 缺件或損壞會非零結束
- 不包含完整公開資料集、模型權重、訓練輸出或使用者資料

老師試用前另有較大的 local-only profile。它不進一般 CI，也不會進 Git：

```bash
poetry run -- python scripts/dev/fetch_public_eeg_fixtures.py \
  --profile teacher-preflight
poetry run -- python scripts/dev/fetch_public_eeg_fixtures.py \
  --profile teacher-preflight --verify-only
timeout 600s prlimit --core=0 -- poetry run -- python \
  scripts/dev/report_teacher_dataset_preflight.py \
  --strict --write-artifacts

# Final gate from a committed product-source checkpoint. This also runs the
# real five-step Qt workflows with missing fixtures treated as failures and
# writes current OpenNeuro screenshots.
timeout 1800s prlimit --core=0 -- poetry run -- python \
  scripts/dev/run_teacher_handoff_gate.py --require-clean-source
```

- pinned manifest 共 `277,106,963 bytes`，程式內硬上限為 `320 MiB`
- profile 總共 10 個 fixture groups：既有 required CI 的 7 組，加上三個獨立資料模型：
  - OpenNeuro ds003061：真實三個 run 的 BIDS / EEGLAB P300，配對三個 `events.tsv`
  - CHB-MIT chb01：臨床長時間 EDF、seizure sidecar 與人類可讀 summary
  - Sleep-EDF ST7011：PSG EDF 與獨立 EDF+ hypnogram
- backend runner 會經真實 `ApplicationService` 跑 scan、preview、validate、apply 與
  OpenNeuro epoch handoff，並逐 run 比對來源與匯入後的 `(sample, class label)` digest；
  artifact 預設寫到
  `build/dev-artifacts/teacher-data-preflight/teacher-dataset-preflight.{json,md}`
- final gate 會先驗證 exact manifest，再跑 backend runner 與不可 skip 的真 Qt wizard，
  screenshot / evidence 預設寫到 `build/dev-artifacts/teacher-data-preflight/ui/`
- OpenNeuro case 是 reviewed class-label placement evidence；CHB-MIT 與 Sleep-EDF
  目前只宣稱 raw import 與 sidecar 分類正確
- CHB-MIT seizure sidecar 與 Sleep-EDF hypnogram 尚不會自動轉成 supervised labels；這是
  明確產品邊界，不可由 raw import PASS 外推

若要專門測試 BIDS subject selector，可使用三個真實 P300 subjects 的 local-only profile。
它保留 ds003061 的 `sub-001`，並加入完整的 `sub-002`、`sub-003`；每個 subject 都有三個
EEGLAB runs 及相對應的 BIDS sidecars：

```bash
poetry run python scripts/dev/fetch_public_eeg_fixtures.py \
  --profile p300-multisubject
poetry run python scripts/dev/fetch_public_eeg_fixtures.py \
  --profile p300-multisubject --verify-only
```

- exact pinned profile：`68` files、`569,171,066 bytes`
- BIDS root：`tests/fixtures/data/public/openneuro-ds003061-p300/`
- 手測時選擇 `Import BIDS folder`，subject selector 應列出 `001`、`002`、`003`
- 這個 profile 不屬於 required CI 或 teacher-preflight，不會增加一般 CI 下載量

一般本機 pytest 仍允許在尚未下載 public fixtures 時 skip，方便日常開發。CI 的
`Required Public Multi-Dataset Gate` 不依賴這個 skip：它會先下載 required profile、
執行 `--verify-only` 與 strict dataset matrix，再跑 public IO、BIDS、cross-source
training smoke；因此 required fixtures 缺失時不能顯示綠燈。

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
  - Type: reviewed annotation IO/epoch-only sample; the fixture does not provide
    protocol ground truth that defines `rt` / `square` as supervised classes
- `scan41_short.cnt`
  - Source: MNE testing-data
  - Format: Neuroscan CNT
  - Type: event-rich compact CNT sample
- `test_NO.vhdr`
  - Source: MNE testing-data
  - Format: BrainVision `.vhdr`
  - Sidecars: `test_NO.eeg`, `test_NO.vmrk`
  - Type: compact BrainVision sample for sidecar-format coverage
- `mne-bids-tiny-eeg/`
  - Source: MNE-BIDS `tiny_bids` test data pinned to a Git revision
  - Format: BIDS EEG root with BrainVision `.vhdr/.eeg/.vmrk`, `events.tsv`,
    `events.json`, `channels.tsv`, electrodes, scans, sessions, and participants
    sidecars
  - Type: compact downloaded folder-level BIDS-EEG import, metadata, label
    placement, recipe, and epoch handoff coverage

## Pinned source facts

`report_data_interpretation_format_matrix.py --strict` 會經 product loader 重新量測下表。
`canonical units` 是 MNE channel metadata 的標準單位，`source units` 是 loader 保留的原始單位；
events 是 raw 內嵌 event summary，不把 external carrier 混入分母。

| Fixture | Hz | Channels / types | Canonical / source units | Samples | Embedded events | Import warnings |
| --- | ---: | --- | --- | ---: | --- | --- |
| `physionet-eegmmidb-S008R01.edf` | 160 | 64 / EEG 64 | V 64 / uV 64 | 9,760 | 1 (`T0`) | none |
| `physionet-eegmmidb-S008R04.edf` | 160 | 64 / EEG 64 | V 64 / uV 64 | 19,680 | 30 (`T0`, `T1`, `T2`) | none |
| `bbci-competition-iii-O3VR.gdf` | 125 | 2 / EEG 2 | V 2 / unknown 2 | 729,558 | 2,560 (`768`, `769`, `770`, `781`, `783`, `785`) | 1 RuntimeWarning |
| `sccn-eeglab_data.set` | 128 | 32 / EEG 32 | V 32 / unknown 32 | 30,504 | 154 (`rt`, `square`) | none |
| `scan41_short.cnt` | 400 | 128 / EEG 128 | V 128 / unknown 128 | 3,070 | 6 (`0`, `7`, `109`) | 2 RuntimeWarnings |
| `test_NO.vhdr` | 5,000 | 65 / EEG 65 | V 65 / uV 65 | 2,238 | 0 | none |
| MNE-BIDS EEG `.vhdr` | 5,000 | 69 / EEG 67, misc 2 | V 67, degC 1, none 1 / uV 67, S 1, C 1 | 10,000 | 1 raw comment; external `events.tsv` has 2 rows | none |

固定 warning contract：

- BBCI：`RuntimeWarning: Limited 1 annotation(s) that were expanding outside the data range.`
- CNT：`RuntimeWarning: Could not parse meas date from the header. Setting to None.`
- CNT：`RuntimeWarning: Could not define the number of bytes automatically. Defaulting to 2.`

sampling rate、channel/type/unit、sample/event count、event labels 或 warning
category/message/count 任一漂移，都會使 strict matrix 失敗。

目前這組 public baseline 已覆蓋：

- EDF
- GDF
- EEGLAB `.set`
- CNT
- BrainVision `.vhdr`
- BIDS EEG folder

其中有 public protocol class semantics、可直接推進到 cross-source one-epoch training smoke
的 fixtures 固定只有：

- `physionet-eegmmidb-S008R04.edf`
- `bbci-competition-iii-O3VR.gdf`

`sccn-eeglab_data.set` 與 `scan41_short.cnt` 固定是 IO/preprocess/epoch-only evidence。
SCCN 的 `rt` / `square` 缺少 public protocol class ground truth；CNT 的可用 epoch 數太少。
兩者都不算 supervised class 或 class-balanced one-epoch training evidence。

可重跑命令：

```bash
/home/administrator/.local/bin/poetry run -- python scripts/dev/run_public_cross_source_training_smoke.py --format markdown
/home/administrator/.local/bin/poetry run -- python scripts/dev/run_public_cross_source_training_smoke.py --format json --strict
```

目前仍停在 import/facade breadth 的 fixture 是：

- `physionet-eegmmidb-S008R01.edf`
- `test_NO.vhdr`

另外 `mne-bids-tiny-eeg/` 是 downloaded folder-level Data Import / BIDS-EEG
fixture；它不是 XBrainLab 自己生成的資料，也不代表 full BIDS validator
compliance，但用來保護 XBrainLab 的 BIDS root scan、`events.tsv` label
carrier、metadata preview、recipe replay 和 epoch handoff。

為什麼保持 local-only：

- 它們能補足 repo 內 checked-in fixtures 沒有涵蓋到的資料來源多樣性
- 它們能補強 public-source format coverage，而不讓 repo 持續膨脹
- 某些來源的再散布邊界不如 repo 內自製 compact fixtures 那麼單純
