# Data Interpretation 目標系統

最後更新：`2026-05-12`

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

## Data Import UX Redesign

2026-05 的人工 walkthrough 顯示：目前 preview 雖然已有 scan / preview / validate / apply
生命週期，但使用者心智模型仍被工程欄位打斷。目標 UI 應改成 data import wizard，而不是把
scan result、metadata、label matching、format capability 和 recipe trace 全塞在同一個 preview
panel。

新版流程應分成五個使用者任務：

| Step | 使用者目標 | 第一層 UI 應顯示 | 不應在第一層暴露 |
| --- | --- | --- | --- |
| Choose EEG Data | 選要匯入的 EEG data。 | `Import file`、`Import folder`、`Import BIDS folder`；清楚顯示 selected files 和 scan location。 | scan root implementation、source_kind raw value。 |
| Load Labels | 載入要和 EEG 對應的 labels / events。 | 自動找到附近 label carrier；提供 `Load label file`、`Load label folder`、`Continue without labels`。 | 假設 label 一定和 EEG 在同一資料夾。 |
| Review Metadata | 檢查 subject / session / task / run。 | metadata table、empty metadata compact state、`Smart Parse`、manual edit。 | 空 metadata 佔滿大表格。 |
| Match Labels | 設定 label 如何套到 EEG。 | Pairing board：每個 selected EEG row 選一個 `Label file`，狀態放在 label 右側；label placement：`Read labels from`、`Use as`、`Place labels by` 和 mode-specific placement panel。 | `Anchor`、`Time`、`Granularity`、`Role`、`Label unit` 作為第一層術語。 |
| Review and Import | 只確認真正需要行動的項目。 | grouped checklist：issue、impact、next action、target step。 | 長串 warning / confirmation / format rows，沒有下一步。 |

這五步可以在同一 dialog 裡用 stepper / tabs 呈現，也可以拆成多個 panel；目標不是增加畫面數量，
而是讓每個畫面只服務一個使用者任務。進階資訊例如 format capability、recipe trace、raw event role、
class map diagnostics 應放在 advanced details，而不是和主操作平起平坐。

資料入口命名也應貼近一般使用者語言：

- Primary actions：`Import file`、`Import folder`、`Import BIDS folder`。
- Label actions：`Load label file`、`Load label folder`、`Continue without labels`。
- Metadata actions：`Smart Parse metadata`、`Edit metadata`。
- Advanced / reuse actions：`Load import recipe`、`Save import recipe`、format diagnostics。

`Review and Import` 不應只是問題清單。每一項都要回答：

- 發生什麼事。
- 會影響什麼。
- 使用者下一步要去哪個 step 或哪個 control 修。
- 是否可選擇 import without labels / import with limited metadata。

### 2026-05-11 first-version baseline

目前已交付第一版 task-oriented step-panel wizard：

- Dataset sidebar 主要入口是 `Import file`、`Import folder`、`Import BIDS folder`。
- dialog 使用 step stack，一次只顯示一個 panel：`Choose EEG Data`、`Load Labels`、
  `Review Metadata`、`Match Labels`、`Review and Import`。
- 每個 step 目前有自己的 task panel：source summary cards、label source/action layout、
  metadata status + edit area、label matching workspace、review action cards。
- footer 將退出和流程導航分開：`Cancel` 在左下，`Back` 和 `Next` / final apply 在右下；
  只有最後的 `Review and Import` step 顯示 primary import / apply action。
- EEG selected scope 和 scan location 用 summary cards 分開顯示。
- 使用者可以 `Load label file`、`Load label folder` 或 `Continue without labels`；額外 label sources
  會重新 scan 並和 auto-discovered carriers 合併。
- Match Labels 第一層分成 pairing board 和 label placement：pairing board 只列 selected EEG，
  每列讓使用者選對應的 `Label file`，狀態放在 label 右側；接著設定
  `Read labels from`、`Use as`、`Place labels by`，並由 placement mode 顯示專屬設定 panel；
  class names 放在同一個 step 內。
- preview / validation command result 會帶 structured action items，UI 以 target step grouping、
  issue、impact、next action 呈現。

這是 step-panel wizard baseline，不代表完整 BIDS support，也不代表所有 downstream supervised
workflow 都已讀取 skip-label limited state。

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
| `label_sources` | 可選。額外 label / event file 或 folder；label 不必和 EEG data 在同一資料夾。 |
| user choices | 可選。使用者在 preview 後選擇 label column、MAT variable、anchor event、class map、task / run 等。 |
| recipe path | 可選。用來重跑或檢查先前保存的資料解讀。 |

輸入設計的原則是：使用者只要給資料位置，系統負責掃描和提出候選解讀；不明確的語意再請使用者確認。
但這不代表 label source 必須被同一次 source scan 找到。真實資料常把 EEG 和 labels 分在不同資料夾，
所以 label source 必須能後加、替換、略過，並保存到 recipe。

## 輸出模型

系統應輸出一份 `DataInterpretation`，它描述 XBrainLab 如何理解這份資料。

`DataInterpretation` 至少包含：

- `source`：資料來源類型、路徑、parser / adapter、資料集名稱或 recipe provenance。
- `files`：納入哪些 EEG files、subjects、sessions、tasks、runs。
- `label_carriers`：label / event 來自 EEG 內建 event、MAT、TXT、CSV / TSV、BIDS events、
  protocol 或 device marker stream；來源可能是自動掃到，也可能是使用者額外 attach。
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

- 目前使用者選擇的是 selected file(s)、folder、BIDS root、device export 或 recipe。
- 若系統用 common parent folder scan，UI 應把 selected scope 和 scan location 分開顯示。
- 系統找到哪些 EEG files、label carriers、events、metadata。
- 系統建議如何解讀 event roles 和 class map。
- 哪些選擇是 safe，哪些需要 confirmation，哪些 blocked。
- 套用後會影響哪些 downstream state。
- recipe 保存位置與可重跑狀態。

UI 不應只顯示 `Imported` 或 `Labels attached`。這些狀態不足以讓使用者判斷資料是否可被信任。

### Match Labels 的 UI 語言

backend 可以保留 `anchor`、`time_model`、`granularity`、`role` 這些語意欄位，因為 recipe 和
validation 需要精確表示。但第一層 UI 應翻譯成使用者任務語言：

| Backend semantic | First-level UI wording | 使用者理解 |
| --- | --- | --- |
| label carrier path | Label file | label / event 從哪個檔案來。 |
| selected target file | EEG file | 這份 label 套到哪個 EEG。 |
| selected label field | Read labels from | label 在哪個欄位、MAT variable 或 event column。 |
| anchor + time model | mode-specific placement field | label 怎麼對到 EEG：EEG event order、seconds、sample number、event code。 |
| granularity | inferred label unit | Recipe 內部保存一筆 label 代表 trial、event、interval、recording 或 subject；第一層 UI 不要求使用者填。 |
| role | Use as | class labels、event markers、metadata、ignore。 |
| placement_method | Place labels by | label row 是照 EEG event、time field 或 interval 放到 EEG。 |
| duration_field | Duration field | duration / end-time 先保存，之後交給 epoch setup 使用。 |

Match Labels 第一層應先問 `Label source`：

- `Labels inside EEG files`：不顯示 file pairing，也不可沿用外部 label file 的 class values。畫面應固定分成
  `Candidate label events`、`Class names`、`Not used as labels`。`Candidate label events`
  只顯示 EEG 內建 event code、use as、coverage；`Class names` 是可直接填寫的 code -> class
  name 表格；`Not used as labels` 顯示 epoch anchor、artifact、boundary 等不作為 class label
  的 event。若沒有可靠 event-name mapping，不在 candidate table 顯示 name 欄，也不使用
  `Name needed` 充當資料值。
- `Loaded label files`：顯示 `File pairing`、`Label values and placement`、`Class names`
  和 `Check`。使用者應先看到哪個 EEG 對哪個 label file，再設定 `Read labels from`、
  `Use as`、`Place labels by`，以及 mode-specific placement 欄位。`granularity` / label unit
  由 preview 和 placement method 推定並保存到 recipe，不作為第一層使用者欄位。
  `Place labels by` 不應只是通用下拉選單；四種 placement method 應切換成各自的
  task panel：`EEG event order` 顯示 target EEG event 列表，`Label time` 顯示
  label time field，`Label interval` 顯示 start field 與 duration / end field，
  `Label event code` 顯示 label event code field 與 EEG event code matching 目標。
  若 `Place labels by` 是 `EEG event order`，第一層 UI 必須顯示 `Target EEG events`
  和 count check：label rows、selected EEG events、matched、unmatched / unlabeled、
  excluded EEG events。

Loaded label files 的 placement 不能只存在於 UI 選單。backend preview 必須為每個 active
label carrier 產生 method-specific `placement_reviews`，並保存目前使用的 `placement_review`
到 recipe / candidate handoff。第一版要支援的主流 placement 模型是：

- `EEG event order`：`.mat` / `.txt` / sequence label rows 依序套到使用者選定的 EEG event
  subset；review 必須列 label rows、target EEG event count、matched、unmatched label rows、
  unlabeled EEG events、excluded artifact / boundary events。
- `Label time`：CSV / TSV / BIDS events / MAT label row 有 onset、time、sample、latency
  等單一時間欄；review 必須列 numeric row count 和 time range。
- `Label interval`：BIDS events、CSV / TSV 或 MAT 有 start + duration / end / offset / stop；
  Data Import 保存 interval evidence，epoch step 之後再決定 window semantics。
- `Label event code`：label file 有 event_code / marker / trigger / stimulus code，並用這些
  值對 EEG internal event code；review 必須列 label code coverage、matched / missing codes。

預設策略應由資料結構決定：有 duration / end 時優先 interval；有明確 time field 時使用
Label time；沒有 time field 但有 event-code field 時使用 Label event code；只有 label sequence
時才使用 EEG event order。這仍不是 full BIDS support；BIDS inheritance、events.json levels、
channels mismatch、跨 datatype 和複雜 run-dependent semantics 仍需 preview / confirmation。

`Labels inside EEG files` 的 suggested label 不應由單一 dataset 或單一格式 code table
硬編碼決定。它只能是可審查建議，不能自動宣稱 class semantics 正確；UI 必須保留使用者把
event 在 suggested labels 與 other events 之間雙向移動的能力。具體 evidence 規則屬於目前
implementation contract，記在 `docs/architecture/data_pipeline.md`。

`duration_field` 不代表 Data Import 直接決定 epoch 長度。它是 recipe 中保存給後續 Epoch UI
的 timing evidence；epoch step 之後應能用這個欄位建議或限制 epoch window。

若 label 不在 EEG source 底下，UI 必須提供 load label 入口，而不是讓使用者猜為什麼 scan
沒有找到。使用者手動 load 的 label source 必須能在 `Load Labels` step 移除；auto-detected
label carrier 也必須能從本次 import 排除，並保存成 `excluded_label_carriers` choice，不能只在
UI 上隱藏。`Match Labels` 只負責使用已載入且未排除的來源，不負責管理來源清單。若目前沒有 label，也應明確提供
`Continue without labels`，並把 supervised training 能力標成 limited / blocked，而不是讓 import
流程看起來失敗。

如果使用者在 Match Labels 選擇 `Labels inside EEG files`，recipe 必須使用
`label_carrier=embedded_events`，並停止把已載入的外部 label file choices 當成 active label
plan。外部 label source 可以仍然存在於 Load Labels 的來源清單，但不應被 apply 成訓練 label。
同樣地，若 `class_map` 是從 external label carriers 推出來的，例如 `.mat` 裡只有
`1/2/3/4` classlabel，切到 `Labels inside EEG files` 後不應繼續顯示或保存那份 class
map；inside EEG 只能使用 EEG event 本身可解釋的 class/event semantics。

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
