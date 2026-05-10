# BCI/EEG Import 與 Label/Event 設計資料來源

最後更新：`2026-05-04`

## 文件定位

這份文件整理真實 EEG / BCI 使用場景、資料格式、label / event 來源、metadata
結構與常見歧義，作為後續設計 XBrainLab import / label / BIDS / fallback
機制的資料來源。

它不是 deficiency report，也不是 roadmap。本文不主張 XBrainLab 目前已支援
所有案例；也不直接規定最終解法。它的用途是讓後續設計 import wizard、
label preview、BIDS-aware import、recipe、fallback 與 agent tool-call eval 時，
有一份整理過的現實案例基礎。

## 閱讀方式

後續討論設計方案時，先用這份文件回答：

- 使用者實際會拿什麼資料進來？
- label / event 可能藏在哪裡？
- event code 是否真的等於 class label？
- label 的時間單位、粒度、語意是否明確？
- 什麼資訊能自動推論，什麼資訊需要讓人確認？
- 哪些資訊應保存成可重跑的 import recipe？
- 哪些情境應變成 agent tool-call benchmark case？

本文刻意把「案例」和「解法」分開。設計方案應另寫在 target / architecture 文件，
只引用本文中已確認有代表性的現實模式。

## 核心詞彙

| 詞彙 | 本文件中的意思 |
| --- | --- |
| label carrier | label / event 的承載位置，例如 EEG file 內建 event、旁邊的 `.mat`、BIDS `events.tsv`、資料夾命名或 protocol 文件。 |
| event role | event 在實驗中的角色，例如 trial start、cue、class label、response、artifact、boundary、run marker、bad segment。 |
| label granularity | label 對應的單位，例如 sample、event、trial、epoch、segment、session、subject。 |
| event semantic | event code 或文字描述的真正意義；它可能需要 protocol / sidecar metadata 才能解讀。 |
| import recipe | 一次成功匯入與 label 對齊所需的可重跑設定，例如 file mapping、selected trigger、class map、time unit、confirmed risk。 |
| auto-apply | 系統不需額外確認即可套用 label / event 的情況。這不是只看格式能不能讀，而是看語意與數量是否足夠明確。 |
| confirmation | 系統能提出候選解讀，但需要使用者確認，例如 event role、外部 label 對齊方式、class map 或 mismatch handling。 |
| blocked | 系統缺少必要資訊，不能安全套用 label / event。 |

## 使用者族群

### BCI 研究者

BCI 使用者通常關心實驗 paradigm，而不是單純檔案格式。

常見族群：

- Motor Imagery / ERD-ERS 使用者。
- P300 / ERP speller 使用者。
- SSVEP / c-VEP 使用者。
- hybrid BCI 使用者，例如 SSVEP + P300 或 EEG + eye tracking。

設計時要注意：

- 同一個檔案內可能同時有 trial start、cue、response、artifact 和 class label。
- Motor Imagery 常需要選擇某個 trial anchor，再以 cue 或外部 label 指派 class。
- P300 的 target 可能不是單一 flash，而是 character、row / column、stimulus repetition
  或 target / non-target hierarchy。
- SSVEP 的 class 可能代表 frequency、phase、target ID 或 symbol，不一定是 event code。
- BCI 線上資料常有 timing latency / jitter 問題；timestamp 和 marker stream 不能只靠
  trial order 解讀。

### EEG / Cognitive Neuroscience 研究者

這類使用者常用 BIDS、OpenNeuro、EEGLAB、MNE、MNE-BIDS、NEMAR 等工具鏈。

設計時要注意：

- 他們通常需要資料夾級 metadata，而不是只開單一 EEG 檔。
- `events.tsv`、sidecar JSON、channel metadata、participants metadata 會共同決定
  label / event 語意。
- EEG file 裡的 event code 可能只是 stimulus id；真正 condition 在 sidecar 或 protocol。
- preprocessing、artifact rejection、epoching 可能改變 event context，原始 event 與
  目前 event 都要能追蹤。

### BIDS Curator / Consumer

BIDS 使用者分成資料整理者與資料消費者。

資料整理者關心：

- dataset 是否符合 BIDS validator。
- `events.tsv` 欄位是否有 JSON 描述。
- `channels.tsv`、`electrodes.tsv`、`coordsystem.json`、`participants.tsv` 是否一致。
- metadata 是否正確放在 inheritance hierarchy 中。

資料消費者關心：

- 如何從 BIDS root 掃描 subject / session / task / run。
- 哪些 runs 具有可用 events。
- `trial_type`、`value`、`HED`、`response_time`、`channel` 等欄位如何轉成可用 label。
- 缺少 sidecar 或欄位語意不完整時，系統如何提示。

BIDS 對 XBrainLab 的意義是 folder-level import，而不是新增一個副檔名。

### 碩士生 / 初學者

初學者常見問題不是不能讀檔，而是讀進來後不知道對不對。

設計時要注意：

- 使用者可能只知道資料集名字，不知道 event code 的實驗語意。
- 使用者可能把 import success 當成 label success。
- 使用者可能不知道該選 trial start、cue 還是 class event。
- 外部 label 數量不一致時，使用者需要看到明確的 count preview。
- UI 需要用可理解的語言說明「系統準備套用什麼」，而不是只顯示 raw array。

### Benchmark / Replication 使用者

這類使用者常用 MOABB、BNCI、PhysioNet、OpenNeuro 或論文附帶資料。

設計時要注意：

- benchmark dataset 通常已有 dataset-specific event map、interval、paradigm。
- replication 需要保存完整 import recipe、split、preprocess、epoch window、class map。
- MOABB 類工具把 dataset metadata 結構化成 subjects、sessions、events、interval、
  paradigm；XBrainLab 若要對齊 benchmark，不能只讀檔案與 label array。

### 自建資料使用者

自建資料可能來自 OpenBCI、BrainFlow、LSL / XDF、CSV、MATLAB 或自寫實驗程式。

設計時要注意：

- channel names、montage、reference、unit 可能不完整。
- marker 可能在 marker channel、另一個 stream、CSV 欄位、log file 或 protocol 文件。
- timestamp 可能是 device time、host time、Unix time、sample index 或 relative seconds。
- XDF / LSL 可以有多個 stream，不同 stream 需要同步；不能假設第一個 stream 就是 EEG。
- 自建資料很常需要 custom recipe，而不是通用 auto-import。

### 臨床 / 長時間 EEG 使用者

臨床與長時間 EEG 資料常見於 seizure、sleep、resting-state、artifact annotation。

設計時要注意：

- label 常是 time interval，不是 trial sequence。
- seizure onset / offset、sleep stage、bad segment、artifact interval 都是 segment-level
  annotation。
- EDF 檔可能很長，不能每次都完整載入或完整訓練。
- montage、channel naming、recording split、clinical note 或 summary file 可能是必要 metadata。

## Label / Event Carrier 類型

### EEG File 內建 Event / Annotation

常見 carrier：

- GDF event table。
- EDF+ annotation。
- BrainVision `.vmrk` marker。
- EEGLAB `.set` event / urevent。
- MNE FIF annotations / events。

設計要點：

- 讀到 event 不代表它是 class label。
- event role 需要分類：trial start、cue、class label、response、artifact、boundary、
  run marker、bad segment、ignored。
- 內建 event 可能已被上游工具改寫；需要保留原始 event summary 和 applied interpretation。

### 旁邊檔案

常見 carrier：

- `.mat`：例如 `classlabel`、`labels`、`y`、`event`、`trial`。
- `.txt`：一列或多列 label sequence。
- `.csv` / `.tsv`：label column、onset / duration / trial_type。
- competition external labels。
- protocol 文件或 readme。

設計要點：

- `.mat` 可能有多個變數，不能只取第一個。
- `.csv` / `.tsv` 可能是 timestamp table，也可能只是 label sequence。
- 外部 label sequence 通常需要一個 anchor event 才能對齊 EEG。
- 數量相同不等於語意正確；數量不同也不一定代表不能用，可能需要選定 trigger 或排除 artifact trial。

### BIDS Structure

常見 carrier：

- `events.tsv`
- `events.json`
- `channels.tsv`
- `electrodes.tsv`
- `participants.tsv`
- task / session / run filename entities
- inheritance metadata

設計要點：

- BIDS 是 dataset root 結構，不是單檔格式。
- `events.tsv` 的 `onset` 和 `duration` 是事件時間基準；`trial_type` 只是可選 condition 欄位。
- `events.json` 才能完整描述欄位語意與 levels。
- `value` 欄位若存在，可能作為 integer event id 的來源。
- BIDS inheritance 代表同一份 metadata 可能套用到多個 subject / session / run。
- BIDS import 應能列出 discovered subjects、sessions、tasks、runs、events columns、
  channel metadata 和 missing sidecar。

### 資料夾命名或 Protocol 文件

常見於學生自建資料：

- `subject01_left_hand.csv`
- `S01/session2/rest.edf`
- `task-mi/run03_labels.txt`
- 實驗說明文件寫著 code `1=left`、`2=right`。

設計要點：

- 這類資料不適合完全 auto-apply。
- 系統可以提出候選 class map，但需要使用者確認。
- 成功確認後應保存 recipe，避免下次重新猜。

## Coverage Classes

### BCI Competition / BNCI / GDF

代表案例：

- BCI Competition IV 2a / Graz motor imagery。
- BNCI motor imagery family。

資料特徵：

- 常見 GDF 檔案。
- event table 可能包含 trial start、cue、artifact、run boundary。
- event position 用 sample index，event duration 也可能有意義。
- training data 可能內含 class cue；testing / evaluation data 可能需要外部 label。

設計觀察：

- 需要把 event role 和 class label 分開。
- 需要支援「選定 trial anchor，再套 external label sequence」。
- 需要顯示 anchor count、label count、artifact trial count、class distribution。
- 需要能保存 selected trigger / ignored trigger / class map。

### PhysioNet EEGMMI / EDF+

代表案例：

- PhysioNet EEG Motor Movement / Imagery。

資料特徵：

- EDF+ annotations 常用 `T0`、`T1`、`T2`。
- `T1` / `T2` 的語意會隨 run / task 改變。
- 同一 subject 多 runs，run type 本身是 label 解讀的一部分。

設計觀察：

- 不能只把 `T1` 永遠當成同一 class。
- import preview 需要顯示 run-level task semantic。
- recipe 需要保存 run-to-class mapping。

### BIDS / OpenNeuro / NEMAR

代表案例：

- OpenNeuro EEG / MEG / iEEG datasets。
- NEMAR 相關 EEG / MEG / iEEG datasets。

資料特徵：

- BIDS root 內有 subject / session / task / run 階層。
- events、channels、electrodes、participants metadata 可能分散在不同層級。
- NEMAR / OpenNeuro 生態常結合 BIDS 與 HED event descriptions。

設計觀察：

- XBrainLab 入口應是 scan BIDS root。
- 需要先做 dataset summary，再讓使用者選 subject / session / task / run。
- label preview 要顯示 event columns、levels、missing fields、validator / parser warnings。

### EEGLAB `.set`

資料特徵：

- `EEG.event` 保存目前事件。
- `EEG.urevent` 保存原始事件脈絡。
- `boundary` event 可由 artifact rejection 或 concatenation 自動產生。
- epoched datasets 的 event context 和 continuous datasets 不同。

設計觀察：

- `boundary` 通常不應當成 class label。
- 原始 event 和目前 event 都可能有意義。
- import preview 應顯示 event type counts、boundary counts、epoch status。

### BrainVision `.vhdr/.vmrk/.eeg`

資料特徵：

- `.vhdr` 是 header entry。
- `.vmrk` 保存 marker。
- marker 可能是 stimulus、response、sync、new segment、comment。

設計觀察：

- marker role 需要分類。
- stimulus marker 不一定直接等於 class；response marker 也不應混入 class event。
- New Segment / Sync 類 marker 應作為 recording structure metadata，而不是訓練 label。

### MOABB Benchmark Datasets

資料特徵：

- MOABB 以 dataset class 描述 subjects、sessions、events、interval、paradigm。
- paradigm 包含 imagery、P300、SSVEP 等。
- 不同 paradigm 對 trial、class、epoch window 的定義不同。

設計觀察：

- MOABB 是很好的 metadata / adapter 參考，不只是資料下載器。
- XBrainLab 若要支援 benchmark replication，應能保存 dataset code、paradigm、event map、
  interval、subject / session selection。

### P300 / ERP Datasets

資料特徵：

- trial 可能是一個 flash，而不是一個完整 spelling character。
- target / non-target 可能依使用者注視的 key 或 character 決定。
- event stream 中常有 stimulus id、response、block、sequence、target metadata。

設計觀察：

- label hierarchy 需要保留：flash -> target/non-target -> character / command。
- 若只保留 binary label，可能丟掉後續分析需要的 stimulus context。

### SSVEP / c-VEP Datasets

資料特徵：

- class 可能代表 flicker frequency、phase、target ID、symbol 或 code pattern。
- trial duration、stimulation frequency、refresh rate、harmonics 都可能是 protocol metadata。

設計觀察：

- event code 需要對應 stimulus metadata。
- import recipe 應保存 target-to-frequency / phase map。
- preview 應顯示 class count 之外的 stimulus metadata。

### Clinical Long-Recording EEG

代表案例：

- CHB-MIT seizure dataset。
- TUH EEG / seizure / artifact 類資料。
- sleep stage / resting-state / pathology decoding datasets。

資料特徵：

- EDF 檔可能很長。
- annotation 常是 onset / offset interval。
- montage、channel list、clinical report 或 summary file 可能是必要 metadata。

設計觀察：

- 需要 segment-level label，不是只支援 event sequence。
- 需要 long-recording import strategy，例如 summary first、lazy preview、segment extraction。
- seizure / sleep / bad segment 不應被硬轉成 trial class。

### Self-Recorded Device Data

代表案例：

- OpenBCI GUI / BrainFlow CSV。
- LSL / XDF recordings。
- 自寫實驗程式輸出的 CSV / MAT / log。

資料特徵：

- BrainFlow 提供統一 board data array，但 channel layout、timestamp、marker channel 依 board 而異。
- OpenBCI GUI / BrainFlow CSV 可能有 marker channel。
- XDF 可包含多個 signal / marker streams；需要同步資訊。

設計觀察：

- 需要先識別 EEG stream、marker stream、sampling rate、timestamp source。
- marker 對齊通常要 preview，不適合直接 apply。
- custom recipe 是必要能力，不是少數例外。

## 統一分析維度

每個 import / label 案例都應用同一組問題整理：

| 問題 | 為什麼重要 |
| --- | --- |
| 資料格式是 file-level 還是 folder-level？ | 決定入口是 open file 還是 scan dataset root。 |
| label / event 存在哪裡？ | 決定 parser、mapping 和 preview 來源。 |
| event code 是否直接等於 class？ | 防止把 trial start、artifact、boundary 當成 class。 |
| 是否混有 trial start、cue、response、artifact、boundary、run marker？ | 決定 event role classification。 |
| label 是 sample index、秒、Unix timestamp，還是 trial order？ | 決定對齊方式與時間單位檢查。 |
| label granularity 是 sample、event、trial、epoch、segment、session、subject？ | 決定資料結構和 downstream task。 |
| 是否需要 sidecar metadata 才能解讀？ | 決定是否可以 auto-apply。 |
| 是否能自動推論？何時必須讓使用者確認？ | 決定 UI / agent 的 confirmation boundary。 |
| 哪些資訊應保存成 import recipe？ | 決定可重跑與可交接程度。 |
| 哪些案例應變成 agent tool-call eval case？ | 決定 thesis tool-call benchmark 的現實覆蓋度。 |

## BIDS 獨立章節

BIDS 必須獨立處理，因為它是資料夾級資料制度，不是單一副檔名。

### BIDS 主要資訊來源

| 檔案 | 設計用途 |
| --- | --- |
| `events.tsv` | 事件表；至少要理解 onset、duration，並檢查 trial_type、value、response_time、HED、channel 等欄位。 |
| `events.json` | 欄位語意、levels、description；決定 trial_type / value 是否能轉成 class map。 |
| `channels.tsv` | channel metadata、bad channels、type、unit。 |
| `electrodes.tsv` / `coordsystem.json` | electrode / coordinate metadata；影響 montage / topomap / source-related visualization。 |
| `participants.tsv` | subject metadata；影響 subject-wise split、group analysis、clinical covariates。 |
| filename entities | subject、session、task、run、acquisition 等索引。 |
| inheritance metadata | 上層 metadata 套用到多個 lower-level files。 |

### BIDS 對 XBrainLab 的設計提醒

- 入口應是 `scan dataset folder`，不是只 `open EEG file`。
- import preview 應先顯示 dataset tree：subjects、sessions、tasks、runs、modalities。
- events preview 應顯示 columns、row count、trial_type / value levels、missing duration /
  unknown onset、HED presence。
- channel preview 應顯示 channel type、unit、bad channel、missing montage。
- parser 應保留 BIDS path entities，讓 downstream split 和 recipe 能按 subject / session / run
  重建。
- 若 BIDS Validator 或 MNE-BIDS parser 提供 warning，應納入 preview，而不是只在 log 裡。

## 從案例抽出的設計問題

本文不直接定義 solution，但目前案例已足以支持後續設計時必須回答下列問題。

### Import Wizard

需要能回答：

- 使用者選的是單檔、資料夾、BIDS root，還是 device export folder？
- 系統找到哪些 EEG files、label files、event tables、sidecar metadata？
- 哪些 files 可直接讀，哪些需要 adapter 或 custom recipe？
- 是否存在多個合理候選 label carrier？

### Label Preview

需要能顯示：

- label carrier 類型。
- event / label count。
- event role candidates。
- class / level distribution。
- time unit / time range。
- selected trigger / anchor count。
- mismatch、missing metadata、ambiguous semantic。
- 將要套用的 mapping 和 downstream invalidation。

### Confirmation Boundary

通常可 auto-apply 的情況：

- BIDS events + sidecar metadata 完整，欄位語意明確。
- EEG file 內 event 已是清楚 class label，且沒有混入其他 role。
- dataset-specific adapter 有明確 protocol，且 counts / metadata 對齊。

通常需要 confirmation 的情況：

- 多個 label-like `.mat` variables。
- sequence label 需要選 EEG anchor trigger。
- event code 混有 trial start、cue、response、artifact。
- run-dependent semantic，例如 `T1` / `T2` 依 run 改變。
- class map 來自資料夾命名或 protocol 文件。

通常應 blocked 的情況：

- 找不到 label carrier，也沒有可用 event。
- label count 和 candidate anchor count 無法合理對齊。
- time unit 不明且無法推論。
- sidecar metadata 缺失到無法判斷 condition。
- 使用者未確認 destructive / downstream-invalidating label overwrite。

### Import Recipe

recipe 至少應能保存：

- data source path / dataset root / selected files。
- source format 與 parser。
- subject / session / task / run selection。
- label carrier path / table / variable / column。
- event role mapping。
- selected anchor trigger。
- class map。
- time unit 與 time origin。
- ignored events / artifact handling。
- count summary 與 confirmed mismatch。
- downstream invalidation note。
- parser / validator warnings。
- source citation 或 dataset adapter name。

### Agent Tool-Call Eval Cases

這些場景應成為後續 agent tool-call benchmark：

- 使用者要求匯入 BIDS folder，agent 應選 scan folder，不是 list single file。
- 使用者要求載入 GDF + external labels，agent 應先 preview labels，不應直接 apply。
- 使用者在未選 anchor trigger 時要求套 label，agent 應請求確認或呼叫 preview。
- 使用者問「這些 events 哪些可以訓練」，agent 應查 state / event summary，不應猜。
- 使用者要求用所有 event 訓練，但其中含 artifact / boundary，agent 應提示風險。
- 使用者載入 PhysioNet EEGMMI，agent 應知道 run-dependent semantic 需要 run mapping。
- 使用者載入 XDF，agent 應先掃 streams 並辨識 EEG / marker streams。

## 附錄：與目前 XBrainLab 的對照

這一節只作後續設計參考，不是本文主軸。

目前 XBrainLab 已有的基礎：

- 支援多種 EEG file loader：`.set`、`.gdf`、`.fif`、`.fif.gz`、`.edf`、`.bdf`、`.cnt`、`.vhdr`。
- label loader 可讀 `.txt`、`.csv`、`.tsv`、`.mat`。
- label import 支援 sequence mode 和 timestamp mode。
- sequence mode 可依 selected event names 過濾 EEG events，再把 external labels 套到 selected
  events 上。
- 部分 workflow 已經能透過 ApplicationService command 執行。

後續設計需要避免的誤解：

- loader 能讀檔，不等於資料集 semantic 已被理解。
- label file 能讀，不等於 label 已正確對齊。
- event count 對得上，不等於 event role 正確。
- training smoke 能跑，不等於 import / label 制度已可支撐研究級使用。

## 參考來源

- [BCI Competition IV 2a description](https://www.bbci.de/competition/IV/desc_2a.pdf)
- [BNCI Horizon datasets](https://bnci-horizon-2020.eu/database/data-sets)
- [PhysioNet EEG Motor Movement/Imagery Dataset](https://archive.physionet.org/pn4/eegmmidb/)
- [BIDS Events specification](https://bids-specification.readthedocs.io/en/stable/modality-agnostic-files/events.html)
- [MNE-BIDS `read_raw_bids`](https://mne.tools/mne-bids/stable/generated/mne_bids.read_raw_bids.html)
- [MOABB documentation](https://moabb.neurotechx.com/docs/index.html)
- [MOABB `BaseDataset`](https://moabb.neurotechx.com/docs/generated/moabb.datasets.base.BaseDataset.html)
- [EEGLAB data structures](https://eeglab.org/tutorials/ConceptsGuide/Data_Structures.html)
- [MNE importing EEG device data](https://mne.tools/stable/auto_tutorials/io/20_reading_eeg_data.html)
- [Lab Streaming Layer time synchronization](https://labstreaminglayer.readthedocs.io/info/time_synchronization.html)
- [BrainFlow data format](https://brainflow.readthedocs.io/en/stable/DataFormatDesc.html)
- [OpenBCI GUI documentation](https://docs.openbci.com/Software/OpenBCISoftware/GUIDocs/)
- [CHB-MIT Scalp EEG Database](https://physionet.org/content/chbmit/1.0.0/)
- [NEMAR / OpenNeuro neuroelectrophysiology ecosystem overview](https://www.nature.com/articles/s41597-023-02614-0)
