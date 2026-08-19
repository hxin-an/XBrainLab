# XBrainLab Agent 目標

最後更新：`2026-08-18`

這份文件是 XBrainLab Assistant 產品目標的唯一權威。Runtime inventory、目前測試集合與歷史
artifact 只能描述 current implementation，不能反推本文件的產品契約。

## 角色與邊界

XBrainLab Assistant 是 app 內的 local-only EEG workflow operator。它負責理解本回合需求、從
backend 發布的候選動作中選一個、通過驗證後交給既有 ApplicationService 或 UI surface，並顯示
一個可信 terminal result。

它不是一般檔案瀏覽器、外部 coding assistant、第二套 workflow engine 或會自動跑完整 pipeline 的
autonomous planner。

產品不變量：

- local model 與 revision 必須精確固定；缺少時 fail closed，不 silent fallback。
- ApplicationService、capability policy 與 application publication 是唯一 workflow truth。
- 每個 user turn 最多一個 tool 或一個 `respond_to_user`；成功、blocked、取消或失敗都結束 turn。
- GUI decision 由既有 dialog／panel 的使用者操作完成；模型不代填高影響選項。
- tool result 直接使用 trusted backend／UI public result，不再交給 Granite 改寫。

## Authority layers

- **Runtime compatibility inventory**：source 中可註冊的 implementation；只支援 migration、debug 或
  legacy callers。
- **Current model-facing projection**：目前 product prompt 實際發布的集合；由
  [current architecture](../architecture/agent.md) 描述。
- **Approved target surface**：只由下方 intent ledger 的 18 個核准工具組成。

名稱、membership、參數、execution kind、owner、confirmation 或 terminal result 任一改變，都是
public product contract decision；必須先更新本文件並取得使用者確認。

## Target intent ledger

### GUI completion tools

下列七個工具對模型都是零參數。Tool 只請求既有 GUI；真正選擇、preview、apply、confirmation 與
cancel 都由該 GUI owner 完成。`opened`／`accepted` 不是成功，只有 correlated
`completed`、`cancelled`、`blocked`、`unavailable` 或 `failed` 能結束 turn。

| Tool | Published stage | Existing owner／authoritative side effect | Terminal evidence |
| --- | --- | --- | --- |
| `import_eeg_data` | `empty` | Data Import chooser、Data Interpretation lifecycle、reviewed ApplicationService apply | import applied、cancelled、blocked 或 failed |
| `select_channels` | `data_loaded` | Dataset Channel Selection dialog；`PreprocessCommand(SELECT_CHANNELS)` | selected channels applied、cancelled、blocked 或 failed |
| `set_montage` | `epoch_ready`、`dataset_ready`、`trained` | Montage Settings；`ApplyMontageCommand` | montage applied、cancelled、blocked 或 failed |
| `create_epochs` | `data_loaded`、`preprocessed` | Epoch Settings；`CreateEpochCommand` | epochs created、cancelled、blocked 或 failed |
| `configure_dataset_split` | `epoch_ready`、`dataset_ready`、`trained` | Dataset Split dialog；`SaveDatasetSplitCommand` | split saved／datasets generated、cancelled、blocked 或 failed |
| `select_model` | `epoch_ready`、`dataset_ready`、`trained` | Model Selection dialog；existing ConfigureTraining command owner | model selection saved、cancelled、blocked 或 failed |
| `configure_training` | `epoch_ready`、`dataset_ready`、`trained` | Training Settings dialog；existing ConfigureTraining command owner | training settings saved、cancelled、blocked 或 failed |

七個 names 共用既有 typed UI handoff registry 與一個 thin adapter。Internal route identity、underlying
command 與 decision fields 由 trusted action contract 固定，不是模型參數，也不建立新 UI owner。

### Direct preprocessing tools

下列五個工具直接走既有 Preprocess command owner。Raw data 保留，因此不加 Assistant confirmation；
缺少必要參數時用 `respond_to_user` 詢問，不套 default、不改走 GUI、不使用 standard bundle。
Backend 仍負責 Nyquist、range、state、resource 與 scientific precondition。

| Tool | Required parameters | Published stage | Terminal |
| --- | --- | --- | --- |
| `apply_bandpass_filter` | `low_freq: number`、`high_freq: number` | `data_loaded`、`preprocessed` | applied 或 typed blocked／failed result |
| `apply_notch_filter` | `freq: number` | `data_loaded`、`preprocessed` | applied 或 typed blocked／failed result |
| `resample_data` | `rate: number` | `data_loaded`、`preprocessed` | applied 或 typed blocked／failed result |
| `set_reference` | `method: string`，必須符合 backend-supported contract | `data_loaded`、`preprocessed` | applied 或 typed blocked／failed result |
| `normalize_data` | `method: "z-score" \| "min-max"` | `data_loaded`、`preprocessed` | applied 或 typed blocked／failed result |

### Lifecycle tools

| Tool | Parameters | Published stage | Confirmation／terminal |
| --- | --- | --- | --- |
| `start_training` | none | `epoch_ready`、`dataset_ready`、`trained` | backend 缺 setup 時 blocked；ready 時使用既有 start confirmation，之後以 real training terminal 收尾 |
| `stop_training` | none | `training` | 只接受使用者明確要求；stopped／cancelled／idle-blocked terminal |
| `reset_preprocessing` | none | raw data 存在且未 training | 使用既有 destructive confirmation；保留 raw、清除 derived state |
| `clear_training_history` | none | history 存在且未 training | 使用既有 destructive confirmation；清除 runs/history，不清除可重用 setup |

Confirmation、resource receipt、generation token與 filesystem path 都由 trusted product code處理，
模型不得輸出或保存。

### Owned analysis action

`compute_saliency`是唯一可由Assistant提出的analysis execution tool：

- 參數固定為空object，只在`trained`stage發布。
- 一律先使用既有Assistant confirmation card；取消後不得執行或continuation。
- 批准後開啟Visualization的Saliency Map，使用該panel當下合法的completed run、method與settings；
  模型不選擇也不保存這些值。
- 執行仍由既有VisualizationPanel、ApplicationService／AnalysisService與resource confirmation擁有；
  Assistant adapter不建立第二個command、readiness或operation owner。
- 只有同一owned operation id的`completed`、`cancelled`、`blocked`或`failed`能結束turn；opened、
  button clicked、scheduled或其他operation terminal都不是成功。
- 沒有合法completed run、selection stale或已有saliency operation時blocked，不silent fallback或重複啟動。

### Navigation

`switch_panel` 是唯一 navigation tool：

- `panel_name` 必須是 `dataset`、`preprocess`、`training`、`evaluation` 或 `visualization`。
- `view_mode` 只允許搭配 `visualization`，值為 `saliency_map`、`spectrogram`、
  `topographic_map` 或 `3d_plot`。
- 所有可靠 stage 都發布；backend state unavailable 時仍可發布。
- MainWindow materialization 的 correlated ready／failed callback 才是 terminal。
- Visible result 必須包含實際 destination，例如 `Opened Saliency Map`，不能一律顯示 generic
  Visualization 文案。

### Retired model-facing surface

下列名稱不屬於 target model surface：

- `list_files`、`get_dataset_info`、`query_state`。
- `load_data`、`attach_labels`。
- `scan_source`、`preview_interpretation`、`validate_interpretation`、`apply_interpretation`。
- interpretation recipe save／reload wrappers。
- `apply_standard_preprocess`。
- current `set_model`、parameterized `configure_training` wrappers。
- current `evaluate`、`visualize`、`saliency` wrappers。
- `reset_session`。

相關 backend services 與 GUI consumers 保留；只有 Assistant wrapper 在 caller inventory 為空後物理
刪除。不得新增 runtime fallback 或第二個 compatibility path。

## Backend-owned stage contract

沿用既有 `PipelineStage`，不建立 Agent state machine：

| Stage | Backend meaning | Published target behavior |
| --- | --- | --- |
| `empty` | 無 raw data | Import、Switch |
| `data_loaded` | 有 raw、尚無 derived preprocessing | Channel、五項 direct preprocess、Epoch、Switch |
| `preprocessed` | Channel 或任一 preprocess 已成功 | 五項 direct preprocess、Epoch、Reset、Switch |
| `epoch_ready` | 已有 supervised epochs，但 split／model／training settings 尚未全部完成 | Montage、三項 setup tools、Start、Reset、Switch |
| `dataset_ready` | saved split、model、training settings 三項全部完成 | setup 可修改；Start confirmation；Montage、Reset、Switch |
| `training` | active training job | Stop、Switch；不發布其他 mutation |
| `trained` | 至少一個 completed run | setup／retrain、Montage、Reset、Clear History、Compute Saliency、results navigation |

`select_channels` 或任一 direct preprocess 成功會自然投影為 `preprocessed`。Raw data可直接建立
Epoch；`CreateEpochCommand`要求raw與合法epoch context，不以preprocessing operation作前置條件，成功後
直接投影為`epoch_ready`。Montage只在epoch後提供、不改變stage。`start_training` 在 `epoch_ready`
可被提出，但backend必須精確回覆缺少的split、model或training settings，不能部分執行。

Stage、setup flags、running state與completed runs都從同一份 immutable ApplicationService
publication產生。若 publication generation 在生成、repair、confirmation或GUI handoff期間改變，
舊 proposal／resolution一律視為 stale。

## Strict model output contract

Granite 每次只能輸出一個 JSON object，且 top level 恰有三個欄位：

```json
{
  "workflow_stage": "preprocessed",
  "tool_name": "create_epochs",
  "parameters": {}
}
```

禁止 Markdown fence、前後 prose、array、多個 calls、額外欄位、寬鬆抽取與 legacy fallback。
`workflow_stage` 是對 backend stage 的 acknowledgement，不是 authority。

不執行 tool 時使用保留 branch：

```json
{
  "workflow_stage": "data_loaded",
  "tool_name": "respond_to_user",
  "parameters": {"message": "..."}
}
```

`respond_to_user.parameters` 只能有 `message`。Answer、clarification與blocked reply不建立額外
decision enum。

Repair budget 是 initial generation 加最多兩次 repair：

- 可 repair malformed JSON、wrong stage、unpublished tool、extra／invalid parameter。
- 只有 user text 已含完整值時才能 repair parameter；不得發明缺少的科學或訓練值。
- backend generation 改變時 discard proposal，重新讀取最新 publication。
- backend blocked、confirmation cancel、GUI cancel／fail或任何 side effect 後不得 repair。
- 同一訊息要求多個 mutation時不部分執行；用 `respond_to_user` 請使用者選第一個。

## Prompt、state card與RAG

每回合 prompt 只含：

1. 固定 policy 與 strict envelope。
2. backend stage 發布的 target schemas。
3. hidden minimal state card。
4. 最新 user message。
5. 最多上一則 Assistant-visible message。

State card 只投影 ApplicationService publication：

- always：stage、internal backend generation、`state_reliable`。
- stage-relevant counts／readiness。
- setup stage：split、model、training-settings flags與missing list。
- training：model、running與短進度。
- trained：finished run count、results available。

不放 file paths、完整 channels、完整 settings、diagnostics、recommended next step、full capability map、
舊 tool output或 pending intent。

RAG／examples規則：

- stage 只發布 1–3 tools 時，使用每個 visible tool 一個 compact canonical example，不做 semantic
  retrieval。
- stage 發布 4 個以上 tools 時，只在該 stage 的 approved examples中取 top 2。
- example retrieval failure時退回schema／format，不擴大tool surface。
- example不能授予capability、confirmation或continuation權限。

Backend state不可靠時，state card固定為 `workflow_stage: "unavailable"`、
`state_reliable: false`，只允許 `respond_to_user` 與 `switch_panel`；不沿用 stale tool set。Granite
runtime本身失敗時不做生成，ChatPanel顯示local runtime error。

## Verification、execution與presentation

Verification順序固定為：strict schema → backend generation／stage → target publication → parameter
schema → ApplicationService capability → confirmation。Prompt與UI不可成為alternate readiness engine。

GUI completion使用既有 pending interaction與request correlation。`accepted`、`navigated`、
`command_pending`或`deferred_to_ui`是否terminal必須依execution kind判斷：GUI completion只能等實際
dialog outcome；pure navigation則等panel/subview materialized。

Visible result使用既有Assistant bubble與confirmation card：

- 一個concise trusted backend／UI public message。
- 不顯示raw JSON、traceback、private path、capability dict或內部token。
- 不讓模型產生下一步建議或再解釋tool output。

## Diagnostic walkthrough target

`--tool-debug` 必須能在完全不建立或載入Granite的情況下使用正常ChatPanel、MainWindow、
ApplicationService、ToolExecutor、confirmation與UI correlation。

- Debug launch顯示slim banner／step progress；normal launch不變。
- Enter只peek目前step；前一步terminal、無pending interaction且navigation idle後才commit並前進。
- Failure留在同一步，可retry；`confirmed=true`不得繞過真confirmation UI。
- 三份pure-data profiles：Complete Workflow、Lifecycle／Navigation、Contract Failures。

Diagnostic mode只是一個既有runtime lifecycle的no-generation transport狀態，不是新的workflow owner、
command policy或fake backend。

## Candidate validation與claims

Engineering candidate suite在新增`compute_saliency`後仍固定為50 cases：36個positive cases（18個
target tool各2個）加14個challenge diagnostics。Challenge必須包含五個missing-parameter、跨stage
lifecycle、out-of-stage、general、ambiguous與multi-mutation；raw score保留用來暴露2B模型限制，不把
Host拒絕冒充raw-model accuracy。Candidate gates：

- invalid／out-of-stage／stale execution、cancel後continuation與multi-mutation partial action皆為0。
- 36個positive全部得到exact final tool＋parameters，且五個direct preprocess的值都能從latest user
  request驗證；完整值不新增confirmation。
- 五個missing-parameter cases可以由模型直接`respond_to_user`，或由模型提出tool後被同一production
  parameter-origin guard轉成一般Assistant追問；兩條路徑都必須零ApplicationService／ToolExecutor
  execution，且追問指出缺少的欄位。
- Candidate gate要求36/36 positive、其中10/10 direct preprocess origin checks，以及5/5
  missing-parameter composed outcomes；其餘9個raw challenge
  結果完整保存為known limitations，不加入promotion分母，也不得宣稱已解決。使用者已接受具完整明確
  參數的ambiguous／multi-action request可能只執行模型選中的一個action；one-command cap後不得自動
  執行第二項。
- 真model safe E2E：Switch Dataset、Import GUI、direct Resample。

這些是產品候選gate，不是thesis benchmark或安全零容忍。Thesis evidence另由frozen source、case set、
runner、model revision與至少三次repeat定義；mock、host-assisted guard、dashboard或單次walkthrough
不能宣稱raw-model accuracy。

目前產品在完成migration與同一exact-SHA candidate evidence前，不能宣稱Stable v2、18-tool
runtime、model-free walkthrough或Assistant-ready。
