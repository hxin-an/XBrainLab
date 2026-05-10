# Data Interpretation 目標系統

最後更新：`2026-05-04`

這份文件定義 XBrainLab 資料匯入、label / event 解讀、BIDS、recipe、UI / agent
行為的終局目標設計。

它描述的是目標態，不代表目前程式碼已完成。研究材料與現實案例來源請看
`docs/research/bci_eeg_import_label_design_source.md`；目前實際架構與 source 對照請看
`docs/architecture/data_pipeline.md`。

## 核心目標

XBrainLab 的資料入口不應只是 `load file`，也不應只是把 label file attach 到 raw data。
終局目標是：

```text
使用者提供資料位置
  -> 系統建立這份資料如何被理解的 DataInterpretation
  -> 使用者可預覽和確認不明確語意
  -> 系統套用解讀並保存可重跑 recipe
  -> 下游 preprocess / epoch / dataset / training / saliency 能追溯資料語意
```

換句話說，核心產物不是「讀進來的 raw file」，而是可審查、可重跑、可被 UI 與 agent
共用的資料解讀。

## 輸入模型

對使用者來說，理想輸入應該盡量簡單：

```text
source_path
```

`source_path` 可以是：

- 單一 EEG file，例如 `.gdf`、`.edf`、`.set`、`.vhdr`。
- 多個 EEG files。
- 一個普通資料夾，內含 EEG files、labels、metadata 或 protocol notes。
- 一個 BIDS root。
- 一個 device export folder，例如 OpenBCI、BrainFlow、LSL / XDF、CSV export。
- 一份已保存的 import recipe。

系統可以接受可選輔助資訊，但不能要求初學者一開始就理解所有格式細節：

| 輸入 | 說明 |
| --- | --- |
| `source_path` | 必填。資料位置，可以是 file、folder、BIDS root、device export 或 recipe。 |
| `source_hint` | 可選。`auto`、`file`、`folder`、`bids`、`device_export`、`recipe` 等提示；預設應是 `auto`。 |
| user choices | 可選。使用者在 preview 後選擇 label column、MAT variable、anchor event、class map、task / run 等。 |
| recipe path | 可選。用來重跑或檢查先前保存的資料解讀。 |

輸入設計的原則是：使用者只要給資料位置，系統負責掃描和提出候選解讀；不明確的語意再請使用者確認。

## 輸出模型

系統應輸出一份 `DataInterpretation`，它描述 XBrainLab 如何理解這份資料。

`DataInterpretation` 至少包含：

- `source`：資料來源類型、路徑、parser / adapter、資料集名稱或 recipe provenance。
- `files`：納入哪些 EEG files、subjects、sessions、tasks、runs。
- `label_carriers`：label / event 來自 EEG 內建 event、MAT、TXT、CSV / TSV、BIDS events、
  protocol 或 device marker stream。
- `event_roles`：trial anchor、class cue、response、artifact、boundary、run marker、bad
  segment、ignored 等角色。
- `class_map`：label code / text 對應的 class 名稱。
- `time_model`：sample index、seconds、absolute timestamp、relative timestamp 或 trial order。
- `granularity`：label 對應 sample、event、trial、epoch、segment、session 或 subject。
- `metadata`：subject、session、task、run、sampling rate、channel names、channel order、
  channel type、montage / electrode positions。
- `warnings`：語意歧義、count mismatch、缺 sidecar、time unit 不明、metadata 不足等。
- `confirmations`：使用者確認過的選擇與原因。
- `recipe`：可重跑的資料解讀紀錄。

系統也應在每次 scan / preview / validate 時輸出人能理解的摘要，讓 UI 與 agent 都能清楚說明
「現在系統打算如何理解這份資料」。

## Subject / Session / Task / Run Metadata

subject、session、task、run 不是 load data 後才補的 UI 欄位，而是 Data Interpretation 的核心
語意。它們會直接影響 dataset split、training claim、benchmark replication、saliency report 和
thesis evidence。

資料解讀時應為每個 file / run 建立 metadata preview：

| 欄位 | 說明 |
| --- | --- |
| `file` | 原始 EEG file 或 run source。 |
| `subject_id` | subject identity。 |
| `session` | session / visit / day。 |
| `task` | task 或 paradigm，例如 MI、P300、SSVEP、resting-state。 |
| `run` | run index / acquisition run。 |
| `source` | metadata 來源，例如 BIDS entity、participants.tsv、filename rule、folder rule、header、user override。 |
| `decision` | `safe`、`needs_confirmation` 或 `blocked`。 |
| `reason` | 為什麼可自動採用、為什麼需確認、或缺什麼資訊。 |

常見 metadata 來源：

| 來源 | 預設判斷 |
| --- | --- |
| BIDS `sub-*`、`ses-*`、`task-*`、`run-*` entity | 通常 `safe`，仍要 preview。 |
| BIDS `participants.tsv` / inheritance metadata | 通常 `safe`，但缺欄位要標 warning / limited / blocked。 |
| 明確且一致的檔名規則，例如 `S01_run1.edf` | 通常 `needs_confirmation`，保存 filename parser rule。 |
| 競賽資料命名，例如 `A01T.gdf`、`A01E.gdf` | `needs_confirmation`，因為 subject、session、train/eval split 可能藏在命名語意裡。 |
| folder 結構，例如 `subject01/session2/*.edf` | `needs_confirmation`，保存 folder parser rule。 |
| EEG header metadata | 可用但要顯示來源，通常 preview 後確認。 |
| 無法推論且 downstream 需要 subject / session split | `blocked` 或要求使用者指定。 |

如果使用者要做 subject-wise 或 session-wise split，subject / session metadata 必須先是 `safe`
或已確認。否則系統不能宣稱該 split 或後續 training evidence 可信。

recipe 必須保存 metadata 推論規則與使用者 override：

- 每個 file / run 對應的 subject、session、task、run。
- 使用的 filename / folder parser rule。
- 自動推論與使用者確認的差異。
- metadata 來源與 warning。
- 這些 metadata 如何影響 split、training、evaluation、saliency。

## 資料解讀生命週期

`DataInterpretation` 不能同時代表「候選解讀」和「已套用 truth」。生命週期應分清楚：

| 階段 | 含義 |
| --- | --- |
| `ScanResult` | 系統從 `source_path` 找到的 EEG files、label carriers、events、metadata、BIDS structure 或 device streams。 |
| `InterpretationCandidate` | 系統根據 scan result 建立的候選解讀，例如 event role、class map、time model、label source。 |
| `InterpretationPreview` | 給使用者與 agent 看的摘要，包含 count、class distribution、warnings、需要確認的選擇。 |
| `ValidationDecision` | 對 candidate 的判斷：`safe`、`needs_confirmation` 或 `blocked`。 |
| `AppliedInterpretation` | 已通過 validation / confirmation 並寫入 XBrainLab state 的資料解讀。這才是下游 preprocess / epoch / dataset 的 truth。 |
| `ImportRecipe` | 可重跑、可審查的資料解讀紀錄；它能重建 candidate 並重新 validation，但不應跳過 preview。 |

下游 workflow 不應直接依賴 scan result 或未確認 candidate。只有 `AppliedInterpretation` 能作為
preprocess、epoch、dataset、training 和 saliency 的資料語意來源。

## 統一流程

所有資料來源都應走同一個抽象流程：

```text
scan -> interpret -> preview -> validate -> confirm -> apply -> save recipe
```

| 步驟 | 目標 |
| --- | --- |
| scan | 從 `source_path` 發現 EEG files、label carriers、events、metadata、BIDS structure 或 device streams。 |
| interpret | 依資料結構與已知案例建立候選資料解讀，例如 label source、event role、class map、time model。 |
| preview | 把候選解讀轉成使用者可理解的摘要，顯示 count、class distribution、event roles、warnings。 |
| validate | 判斷候選解讀是 `safe`、`needs_confirmation` 或 `blocked`。 |
| confirm | 對會影響結果、但系統無法完全自動判斷的語意要求使用者確認。 |
| apply | 只套用 `safe` 或已確認的解讀，並更新 XBrainLab workflow state。 |
| save recipe | 保存可重跑、可審查的資料解讀紀錄。 |

這條流程是 UI、in-app agent、headless script 和 MCP external agent 的共同心智模型。任何入口都不應另建一套 label / event 判斷。

## 判斷策略

不使用不可審查的神秘 confidence score。判斷結果應是：

| Decision | 含義 |
| --- | --- |
| `safe` | label / event 語意、count、class map、必要 metadata 都足夠明確，可以套用。 |
| `needs_confirmation` | 系統有合理候選解讀，但該選擇會影響結果，需要使用者確認。 |
| `blocked` | 缺少關鍵資訊，不能可靠套用。 |

常見 `needs_confirmation`：

- GDF + external label sequence，需要選 trial anchor。
- `.mat` 內有多個 label-like variables。
- event code 同時混有 trial start、cue、response、artifact 或 boundary。
- PhysioNet EEGMMI 類 run-dependent `T1` / `T2` semantic。
- BIDS sidecar metadata 不完整，但仍有可解釋候選。
- XDF / LSL 有多個 signal / marker streams。

常見 `blocked`：

- 找不到可用 EEG data。
- 找不到 label carrier，也沒有可用 event / annotation。
- label count 和候選 anchor count 無法合理對齊。
- time unit / time origin 無法判斷。
- class map 無法建立。
- 缺少必要 BIDS metadata，導致 `trial_type` 或 event columns 無法解釋。

這個 decision 是資料解讀 validation，不是 LLM confidence。agent 可以有自己的 confidence gate
來決定是否重送 prompt 或 self-correct，但它不能把 `blocked` 覆蓋成可執行。

## 驗證模型

XBrainLab 需要三層驗證，不能把它們混成一個「agent 覺得可不可以做」：

| 層級 | 驗證對象 | 輸出 | 誰使用 |
| --- | --- | --- | --- |
| Data Interpretation validation | 資料來源、label / event 語意、metadata、recipe | `safe`、`needs_confirmation`、`blocked` | import UI、agent、backend apply step、recipe reload |
| Workflow State validation | 目前 app state、active pipeline、jobs、results、destructive boundary | capability policy | UI command enablement、agent tool exposure、ApplicationService |
| Agent Tool-call validation | LLM 提出的 tool call、schema、參數、confidence、目前 capability | `allow`、`block`、`repair`、`ask_user`、`confirm` | Verification Layer、scorer、agent retry loop |

這三層的責任不同：

- Data Interpretation validation 判斷「這份資料能不能被可靠理解」。
- Workflow State validation 判斷「目前 app 狀態能不能做這個操作」。
- Agent Tool-call validation 判斷「LLM 這次提出的操作是否正確、完整、可執行」。

agent 的 confidence gate 只屬於第三層。低 confidence 可以觸發 prompt retry、self-correction 或
ask user；它不能把資料解讀的 `blocked` 變成 `safe`，也不能繞過 backend capability policy。

### Data Interpretation validation

Data Interpretation validation 的輸入是 `InterpretationCandidate`、user choices 和可選
`ImportRecipe`。它的輸出是 `ValidationDecision`。

它至少要檢查：

- source 是否可讀、是否有可用 EEG data。
- label / event carrier 是否存在，且能和 EEG data 對齊。
- event role 是否已分出 trial anchor、class cue、response、artifact、boundary、run marker、
  bad segment 或 ignored。
- event code 是否直接等於 class；若不是，是否已有可審查的 class map。
- label count 和 anchor count 是否合理對齊。
- time model 是否明確：sample index、seconds、absolute timestamp、relative timestamp 或
  trial order。
- granularity 是否明確：event、trial、epoch、segment、session 或 subject。
- channel names、channel order、channel type、montage / electrode positions 是否足以支撐
  downstream 能力。
- subject、session、task、run 是否足以支撐使用者選擇的 split / training / reporting claim。
- BIDS metadata 缺失應歸為 `warning`、`limited` 或 `blocked`。

這層可以使用 adapter heuristic、known dataset rule、BIDS validator 或 MNE-BIDS 類工具，但每個
判斷都必須留下可讀原因。它不是 LLM 自由推測，也不是不可審查的 confidence score。

### Workflow State validation

Workflow State validation 的輸入是目前 `AppliedInterpretation`、backend state、active jobs 和
completed results。它的輸出是 capability policy。

它至少要判斷：

- 沒有 `AppliedInterpretation` 時，不能 preprocess / epoch / dataset / supervised training。
- 沒有 label / event 對齊時，不能宣稱 supervised dataset 可用。
- dataset 已產生後，不能用一般 data import 覆蓋 active pipeline；必須走 reset / new session /
  fork 類明確 command。
- training job 正在寫入特定 resource 時，不可同時對同一 resource 做破壞性操作。
- evaluation、visualization、saliency 必須綁定到具體 trained result，而不是只看全域 stage。
- 缺 montage / electrode positions 時，saliency topomap 類能力應標成 `limited` 或 `blocked`。

這層應由 backend / ApplicationService 產生，不應由 agent 自己維護第二套狀態。

### Agent Tool-call validation

Agent Tool-call validation 的輸入是 LLM 提出的 `ToolCall`、State Snapshot、capability policy、
Data Interpretation validation result 和 tool schema。它的輸出是 Verification Result。

它至少要檢查：

- tool 是否在目前 Context Assembler 暴露的 capability 內。
- tool 是否仍被 ApplicationService policy 允許。
- required inputs 是否完整，schema / type / range 是否正確。
- 檔案、dataset、label carrier、recipe、model 或 result 是否存在或可解析。
- Data Interpretation validation 是否允許 apply；`needs_confirmation` 必須先問使用者，
  `blocked` 必須停止。
- destructive / long-running / resource-writing command 是否需要 confirmation。
- LLM confidence 是否低於 threshold；低於 threshold 時只能 retry、repair 或 ask user。

驗證失敗時，agent 不應把 raw schema error、tool exception 或 traceback 顯示給使用者。使用者只需要看到
可理解的原因與下一步；developer diagnostics 應寫入 structured history / artifact / log。

### Recipe reload validation

載入 recipe 不等於自動套用。重跑 recipe 應該走：

```text
load recipe -> rescan source -> rebuild candidate -> compare recipe intent -> preview diffs -> validate -> confirm/apply
```

若原資料、metadata、parser 版本或 XBrainLab 版本改變，系統要顯示差異。只有重新通過 validation
或使用者確認後，recipe 才能產生新的 `AppliedInterpretation`。

## BIDS 作為一等入口

BIDS 不應被當成單一副檔名支援。BIDS 是 folder-level 資料制度。

BIDS flow 應該是：

```text
select BIDS root
  -> scan subjects / sessions / tasks / runs
  -> parse events.tsv / events.json / channels.tsv / participants.tsv
  -> apply inheritance metadata
  -> preview dataset-level interpretation
  -> let user confirm task / run / label column / class map if needed
  -> save BIDS-aware recipe
```

BIDS interpretation 應保存：

- BIDS root 與 selected entities：subject、session、task、run、acquisition。
- events columns、row counts、`trial_type` / `value` / HED levels。
- `events.json` 的欄位描述與 levels。
- `channels.tsv` 的 channel type、unit、bad channel。
- `participants.tsv` 的 subject-level metadata。
- inheritance 後實際生效的 metadata。
- parser / validator warnings。

BIDS metadata 不可在 raw data load 後遺失，否則後續 split、training report、saliency
解釋與 thesis evidence 都無法追溯。

BIDS metadata 缺失不應一律 blocked。應分三層處理：

| 等級 | 含義 |
| --- | --- |
| `warning` | 缺失不影響目前資料解讀，只需要記錄，例如非必要描述欄位缺失。 |
| `limited` | 資料可用，但某些下游能力受限，例如缺 montage / electrode positions 時 training 可繼續，但 saliency topomap 應標成 limited。 |
| `blocked` | 缺失會讓 label / event 語意或時間對齊無法可靠解讀，例如必要 event column、time model、class map 或 inheritance metadata 無法判斷。 |

BIDS validation 的目標不是要求資料完美，而是明確說出哪些能力可用、哪些能力受限、哪些操作不能做。

## Recipe

`ImportRecipe` 的本質不是一般 config，而是「這份資料如何被理解」的證據。

recipe 至少應保存：

- source path、source kind、adapter / parser、XBrainLab version 或 commit。
- selected EEG files、subjects、sessions、tasks、runs。
- label carrier path、format、MAT variable、CSV / TSV column 或 BIDS event column。
- event role mapping、selected anchor event、ignored events、artifact handling。
- class map、time unit、time origin、label granularity。
- channel names、channel order、channel type、montage / electrode positions 是否存在。
- count summary：events、selected anchors、labels、excluded trials / segments。
- validation decision、warnings、confirmed choices、blocked reasons if any。
- downstream invalidation：套用此解讀是否會使 preprocess、epoch、dataset、training result 失效。

recipe 必須能被重新載入並重新 preview。重跑 recipe 不應跳過 validation；如果原資料、metadata
或環境已改變，系統要顯示差異。

## Training / Saliency 的位置

Training 和 saliency 不是 Data Interpretation System 的主模組。

Data Interpretation System 的責任是讓資料解讀足夠清楚，讓下游流程可以信任。可靠載入後：

- training 應能追溯 class、trial、epoch、dataset split 和 recipe。
- saliency 應能追溯 trained run、dataset recipe、class map、channel order、channel names、
  montage / electrode positions 和 epoch time window。

如果缺少 montage 或 channel metadata，saliency 應顯示 limited 或 blocked，而不是假裝完整可用。
如果 label / event 解讀不明確，training 不應被宣稱為可信 supervised workflow。

## UI 行為

新 UI 的資料入口應以 Data Interpretation 為心智模型。

UI 應讓使用者看到：

- 目前資料來源是 file、folder、BIDS root、device export 或 recipe。
- 系統找到哪些 EEG files、label carriers、events、metadata。
- 系統建議如何解讀 event roles 和 class map。
- 哪些選擇是 safe，哪些需要 confirmation，哪些 blocked。
- 套用後會影響哪些 downstream state。
- recipe 保存位置與可重跑狀態。

UI 不應只顯示 `Imported` 或 `Labels attached`。這些狀態不足以讓使用者判斷資料是否可被信任。

## Agent 行為

agent 是 Data Interpretation flow 的 operator，不是繞過流程的快捷入口。

agent 應遵守：

- 使用者給資料位置時，先 scan / preview / validate。
- 不直接把 label file 套到資料。
- 不在 interpretation 不明時說資料可以訓練。
- 不把 raw backend exception 或 schema error 當成使用者訊息。
- 遇到 `needs_confirmation` 時，向使用者說明需要確認的具體語意。
- 遇到 `blocked` 時，說明缺什麼資料或 metadata，以及下一步可補什麼。

agent tool-call benchmark 應測它是否能正確操作這條流程，而不是只測自然語言回答像不像。

## 乾淨架構原則

- 新 UI、agent、headless script、MCP external agent 都應使用同一套 Data Interpretation truth。
- 不保留 UI、agent、backend 各自判斷 label / event 的雙重或三重 truth。
- 舊 `load_data` / `attach_labels` 心智模型不是目標架構。
- 任何仍存在的舊入口都不能作為新 UI / agent 的設計依據；終局交付應以乾淨、可維護、
  可驗證的 Data Interpretation flow 為準。
- import success、label readable、event exists、dataset train smoke 是不同 evidence，不能混成同一個 claim。

## 驗收標準

終局設計至少要能覆蓋下列情境：

- GDF + external MAT labels：選 anchor、確認 class map、保存 recipe。
- BCI Competition / BNCI：trial start、cue、artifact、class event 分開。
- PhysioNet EEGMMI：run-dependent `T1` / `T2` 解讀。
- BIDS / OpenNeuro：folder scan、events / channels / participants metadata。
- EEGLAB `.set`：boundary 不可當 class，event / urevent context 不丟失。
- BrainVision：stimulus、response、sync、new segment marker roles 分開。
- P300 / ERP：flash-level event 與 character / target hierarchy 不混淆。
- SSVEP / c-VEP：class map 可對應 frequency、phase、target ID 或 code pattern。
- XDF / BrainFlow：辨識 EEG stream、marker stream、timestamp model。
- Clinical interval：seizure、sleep、bad segment 作為 interval label，而不是 trial class。
- Recipe reload：保存後可重新 preview、validate、apply。
- Agent benchmark：agent 走 scan / preview / validate / confirm / apply，不走直套 label。
- UI walkthrough：使用者能看懂資料如何被解讀、哪些資訊需確認、哪些資訊 blocked。

## 和其他文件的關係

- `docs/research/bci_eeg_import_label_design_source.md`：整理現實案例與資料來源，是本文的依據。
- `docs/target/requirements.md`：定義 XBrainLab 產品需求；本文細化資料入口的終局目標。
- `docs/target/architecture.md`：定義理想系統架構與 command surface；本文定義資料解讀這條能力面的目標心智模型。
- `docs/architecture/data_pipeline.md`：描述目前實際 data pipeline；若和本文衝突，代表目前實作尚未達到目標。
