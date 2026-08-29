# XBrainLab Agent 目標

最後更新：`2026-08-29`

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

## Local model selection contract

Assistant Settings與runtime共用`XBrainLab/llm/core/model_catalog.py`的單一allow-list：

| Role | Exact model | Revision | Visible positioning |
| --- | --- | --- | --- |
| primary | `ibm-granite/granite-4.0-micro` | `56111ae135df9c53a78c99028e7bc24035a9e979` | Granite 4.0 Micro 3B，recommended default |
| lower-memory | `ibm-granite/granite-3.3-2b-instruct` | `707f574c62054322f6b5b04b6d075f0a8f05e0f0` | Granite 3.3 2B，較低資源選項 |

新安裝、缺漏model choice或retired selection解析至primary；已儲存且仍在allow-list的2B choice保持原值。
Settings可完成exact model的install／status／activate／delete與generation settings，但不自行判斷cache或
runtime readiness。選定model若缺少、不完整、OOM或載入失敗，既有catalog／download lifecycle／runtime
owner必須fail closed並顯示對應狀態，不得silent fallback到另一個model。Primary變更不授權改寫現有使用者
的root `settings.json`，也不把downloaded-but-unsupported cache冒充可選model。

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
| `set_montage` | `data_loaded`、`preprocessed` | Montage Settings；`ApplyMontageCommand` | montage applied、cancelled、blocked 或 failed |
| `create_epochs` | `data_loaded`、`preprocessed` | Epoch Settings；`CreateEpochCommand` | epochs created、cancelled、blocked 或 failed |
| `configure_dataset_split` | `epoch_ready`、`dataset_ready`、`trained` | Dataset Split dialog；`SaveDatasetSplitCommand` | split saved／datasets generated、cancelled、blocked 或 failed |
| `select_model` | `epoch_ready`、`dataset_ready`、`trained` | Model Selection dialog；existing ConfigureTraining command owner | model selection saved、cancelled、blocked 或 failed |
| `configure_training` | `epoch_ready`、`dataset_ready`、`trained` | Training Settings dialog；existing ConfigureTraining command owner | training settings saved、cancelled、blocked 或 failed |

七個 names 共用既有 typed UI handoff registry 與一個 thin adapter。Internal route identity、underlying
command 與 decision fields 由 trusted action contract 固定，不是模型參數，也不建立新 UI owner。

`import_eeg_data` 的 action identity 完全由模型 proposal 與 current publication 決定。它是 zero-parameter
GUI handoff，Host 不讀 latest user text 判斷 import、肯定／否定、英文動詞或 object grammar，也不以文字
heuristic 取代模型的選擇。publication、schema、capability、confirmation 與既有 UI handoff 仍是唯一 trusted
boundary；模型把資訊或否定 request 誤判為 import 必須如實記為 model/product accuracy failure，不能由 Host
semantic rescue 隱藏。

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

Notch 的 schema、published stages 與 DSP operation 不因 sampling-rate precondition 改變。既有
preprocess command owner 必須在 MNE prepare 前，從本次 source data 的最低可靠 sampling rate 檢查
`freq < sfreq / 2`；違反時回 typed precondition，包含 requested frequency、sampling rate、Nyquist 與
可採取的下一步。若 sampling rate 無法可靠取得，維持既有 execution，不猜測阻擋。若資料已 resample，
訊息可指示使用者 reset → notch → resample；Assistant 不自動重排或套用這些動作。

### Direct-preprocess bounded Host collection

當模型已提出一個 exact direct-preprocess tool、該 tool 仍由 current publication 啟用時，Host 可使用既有
`AssistantToolInputReceipt` 收集缺少的 **user-authored evidence**。這是 bounded form，不是 general
intent router：它不能由 user text 選 tool、替換 tool、恢復 unavailable capability、推論科學值或執行。
Host 不解析 `use`、`apply`、`run`、`do` 等英文 action verb，也不判斷肯定、否定或 request grammar。generic
「filter data」仍不是 tool identity：模型必須先決定 exact tool，Host 才能建立 receipt。

form 只可處理下列五個已核准 tool 的 required fields，且只接受現有 origin grammar 可證明的值：

| Tool | Bounded form evidence |
| --- | --- |
| `apply_bandpass_filter` | Host 只檢查 model-proposed `low_freq`、`high_freq` 是否各自出現在 latest user text 的 Arabic decimals；tool identity 和 low/high mapping 都是模型責任，Host 不解析 `bandpass`、`filter`、action verb 或 request grammar。receipt 首次沒有 assigned field 時，兩個 bare decimal cutoffs 以 `min → low_freq`、`max → high_freq` 收集；單一 bare cutoff 暫存為 unassigned evidence。已有一個 verified field 時，一個 bare cutoff 只填 sole remaining field，既有 schema/range validation 仍決定是否可執行。 |
| `apply_notch_filter` | 一個 user-proven decimal `freq`。 |
| `resample_data` | 一個 user-proven decimal `rate`。 |
| `set_reference` | 一個符合既有 backend-supported reference contract 的 user-proven `method`。 |
| `normalize_data` | 一個 user-proven `method`，僅 `z-score` 或 `min-max`。 |

receipt 可保存已驗證 fields 與 bandpass 的單一 unassigned cutoff evidence；這是既有 receipt 的最小 field
extension，不新增 receipt type、queue、state machine 或 owner。已驗證 field immutable：任何 correction、
contradiction、invalid value 或 mixed ambiguous evidence 都清除 receipt，使用者必須以新 request 重啟。publication
change、explicit cancel、new chat、topic switch、different tool 或 reply budget exhausted 也一律清除 receipt，零
execution。word-number parsing（例如 `fifty hertz`）不屬於此 contract，保持 fail closed。

form 收齊 fields 後，Host 必須取得 fresh publication，並以 receipt 原有 exact tool identity 與 verified
parameters 走既有 strict schema、range、publication、capability、confirmation 與 one-action checks。它不建立
alternate execution path，也不採用模型臆測的 values；完成 receipt 不得再要求模型輸出同一 JSON，並且零 RAG、
零 LLM generation。不同 tool、stale publication、explicit cancel 或任何未完成 form 均不得藉 receipt 執行。

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

| Stage | Backend meaning | Target candidates before capability filtering |
| --- | --- | --- |
| `empty` | 無 raw data | Import、Switch |
| `data_loaded` | 有 raw、尚無 derived preprocessing | Channel、Montage、五項 direct preprocess、Epoch、Switch |
| `preprocessed` | Channel 或任一 preprocess 已成功 | Channel、Montage、五項 direct preprocess、Epoch、Reset、Switch |
| `epoch_ready` | 已有 supervised epochs，但 split／model／training settings 尚未全部完成 | 三項 setup tools、Start、Reset、Switch |
| `dataset_ready` | saved split、model、training settings 三項全部完成 | setup 可修改；Start confirmation；Reset、Switch |
| `training` | active training job | Stop、Switch；不發布其他 mutation |
| `trained` | 至少一個 completed run | setup／retrain、Reset、Clear History、Compute Saliency、results navigation |

`select_channels` 或任一 direct preprocess 成功會自然投影為 `preprocessed`。Channel與Montage都在
`data_loaded`／`preprocessed` publication中可用，且在Epoch成功後隨即消失；這不縮限既有GUI/backend的較寬
capability。Raw data可直接建立Epoch；`CreateEpochCommand`要求raw與合法epoch context，不以preprocessing
operation作前置條件，成功後直接投影為`epoch_ready`。`start_training` 是 `epoch_ready`
stage candidate，但split、model或training settings未齊時由同一publication capability排除schema並在
unavailable reference精確說明缺項，不能部分執行；全部ready後才成為callable。

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

只有 parser 能證明 raw output 含兩個以上相鄰、各自完整的 top-level JSON objects 時，它才是獨立的
fail-closed classification：不得進入 first-command selection、format retry、receipt admission、confirmation、
UI handoff 或 execution。Host 直接輸出可信的單一動作回覆，例如「I can perform one action at a time. Which
action should I do first?」。top-level array 與其他無法證明為上述相鄰完整 objects 的 malformed JSON 維持既有
strict format rejection／有限 repair budget；不能以 error-string heuristic 把它誤判為 multiple action。

不執行 tool 時使用保留 branch：

```json
{
  "workflow_stage": "data_loaded",
  "tool_name": "respond_to_user",
  "parameters": {"message": "..."}
}
```

`respond_to_user.parameters` 接受兩種 strict shape：一般 answer／blocked reply 為
`{"message": "..."}`；只有模型已精確辨識一個目前 callable 的 direct-preprocess action、且只缺
該 schema 必要欄位時，clarification 可為
`{"message": "...", "pending_action": "<exact direct tool>", "missing_inputs": ["<required field>", ...]}`。
這仍是 no-execution branch，不增加 top-level field、tool 或 decision enum。`pending_action` 不得用於
generic filter／模糊 action，Host 不從 user text 或 bubble 推測它；模型必須先以一般回覆請使用者選定
exact action。

符合上述 typed clarification 的 response，或模型已提出缺少值的 direct tool 時，Host 可以在零 execution
的具體追問旁建立 typed tool-input receipt。Receipt 只保存 exact tool ID、實際缺少欄位、
可由 user 原文驗證的 values、bounded question evidence、prompt-time publication generation 與最多兩次
parameter reply budget；不得保存或授權模型臆測的參數。它不是新的 model output branch，也不改變三欄
envelope。

Repair budget 是 initial generation 加最多兩次 repair：

- 可 repair malformed JSON、wrong stage、unpublished tool、extra／invalid parameter。
- 只有 user text 已含完整值時才能 repair parameter；不得發明缺少的科學或訓練值。
- backend generation 改變時 discard proposal，重新讀取最新 publication。
- backend blocked、confirmation cancel、GUI cancel／fail或任何 side effect 後不得 repair。
- 同一訊息要求多個 mutation時不部分執行；用 `respond_to_user` 請使用者選第一個。

## Prompt、state card與RAG

每回合 prompt 只含：

1. 固定 policy 與 strict envelope。
2. backend stage 與同一generation capability都允許的 target callable schemas。
3. 已註冊但本回合不可呼叫的target action reference；每項只有stable tool ID與bounded public reason，
   不含schema，也不是合法output candidate。
4. hidden minimal state card。
5. 最新 user message。
6. 最多上一則 Assistant-visible message。

Callable集合固定為approved stage membership、同一份ApplicationService publication的enabled
`ToolAvailability`與目前registry／target membership的交集。其餘已註冊target tools只可出現在明確分隔的
unavailable-action reference：backend capability disabled時沿用同一publication的public reason；capability
enabled但target stage未發布時，使用「此action在目前workflow stage不可呼叫」的bounded projection reason。
Confirmation-required但enabled的action仍是callable，不得列為unavailable。

Unavailable reference不建立新tool、schema、readiness owner、RAG example、confirmation、GUI handoff或
execution permission。模型被問到這些action時應以`respond_to_user`說明對應blocker，不得改呼叫前置或
替代action；若模型仍輸出該stable tool ID，既有`PromptToolPublication`／attempt admission以同一backend
generation與同一reason fail closed。Prompt projection不加入general semantic Host router，也不以文字
heuristic推翻另一個當下確實callable的model proposal。

State card 只投影 ApplicationService publication：

- always：stage、internal backend generation、`state_reliable`。
- stage-relevant counts／readiness。
- setup stage：split、model、training-settings flags與missing list。
- training：model、running與短進度。
- trained：finished run count、results available。

不放 file paths、完整 channels、完整 settings、diagnostics、recommended next step、full capability map、
舊 tool output或一般pending intent。receipt 不投影進 prompt；它只在 Host lifecycle 中保存 verified values，
並且不能恢復 stale capability。

RAG／examples規則：

- stage 只發布 1–3 callable tools 時，使用每個 visible tool 一個 compact canonical example，不做 semantic
  retrieval。
- stage 發布 4 個以上 callable tools 時，只在該 stage 的 approved examples中取 top 2。
- example retrieval failure時退回schema／format，不擴大tool surface。
- unavailable-action reference永遠不提供example，也不進RAG allowed tool names。
- example不能授予capability、confirmation或continuation權限。

Backend state不可靠時，state card固定為 `workflow_stage: "unavailable"`、
`state_reliable: false`，只允許 `respond_to_user` 與 `switch_panel`；不沿用 stale tool set。Granite
runtime本身失敗時不做生成，ChatPanel顯示local runtime error。

## Verification、execution與presentation

Execution verification順序固定為：strict schema → backend generation／stage → target publication → parameter
schema → ApplicationService capability → confirmation。對 direct preprocess 的 schema-incomplete proposal，Host 可先做
zero-execution Arabic-decimal membership admission，以保存 user-proven fields 到既有 receipt；receipt 完成後仍依上述
完整順序重跑，任何 model-mapped reversal 都由 schema/range 拒絕。Prompt與UI不可成為alternate readiness engine。

Direct-preprocess clarification 的第一個 action identity 由模型選擇；receipt-bound form 只把 latest user
evidence累積成該 receipt 的 fields，且不採用模型、prompt、history 或 default 的 value。收齊 fields 後，Host
以 fresh publication 和 receipt 的同一 exact tool 重建 parameters，依上述固定順序重跑 schema、range、current
publication、capability、confirmation 與 one-action checks；不再次問模型。不同 action／topic、explicit cancel、
stale publication、new chat、stop、close 或第三次 parameter reply 都清除 receipt，零 execution。
同 action 的 NO_TOOL、single malformed envelope 或尚缺值只可在剩餘 budget 內維持既有 requeue semantics；
proven adjacent-complete-object multiple proposal 遵守 strict-output contract 的直接 choose-one terminal，不能
requeue 成 action。

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

Engineering candidate的active suite固定為81個英文cases：36個positive cases（18個target tool各2個）、
14個challenge、24個no-action precision與7個controller-backed clarification trajectories。Challenge必須包含
五個missing-parameter、跨stage lifecycle、out-of-stage、general、ambiguous與multi-mutation；raw score保留
用來暴露選定模型限制，不把Host拒絕冒充raw-model accuracy。中文intent／verifier可作未承諾相容基礎，
不屬於active evidence。Candidate gates把raw model、Host safety與product outcome分開報告：

Evaluator v11 保留第一次未受 Host collection／recovery 影響的 raw score，另將 post-recovery score 只作
diagnostic；candidate raw-model gate 只讀第一次 generation。candidate 判定仍必須走與產品相同的
structured-decision token resolver、strict parser 及最多兩次一般 format recovery；proven
adjacent-complete-object multiple proposal 是直接 Host choose-one terminal，不屬於可修成 action 的 recovery。
每次 response／taxonomy 都留在 artifact，最後一個 accepted、blocked、choose-one 或 exhausted presentation
outcome 才是 product score。format
recovery 只修 envelope，不得把 semantic tool-selection failure 重分類為通過。

v11 report 固定保留 81 個英文 case（36 positive、14 challenge、24 precision、7 clarification）的
denominator、case identity 與既有 raw gate；不得用新增 Host rescue、替換 case 或降低 required count 改善分數。
每個 row 必須以同一 controller/pending boundary 依序記錄：

1. first raw model response、strict-envelope taxonomy 與 raw score；
2. first-turn Host admission（current publication、parameter value-origin outcome、receipt created 或
   rejected）；
3. 每一個 follow-up raw response 與 receipt form transition（bound、unassigned、reconstructed、requeued 或
   cleared）；
4. receipt-direct reconstructed parameters、normal verification／confirmation／handoff decision，
   以及可信 product terminal。

Evaluator 不得直接建構 `AssistantToolInputReceipt`、手動塞入 pending coordinator、合成 verified parameters
或把 source raw、follow-up raw 與 product outcome 互相計分。它可使用 product-equivalent controller harness
觀察 receipt 與 terminal，但 source raw score、Host safety／admission、follow-up diagnostic 與 product outcome
必須是分開欄位。focused natural import dispatch 與 adjacent-complete-object choose-one probes 是額外
deterministic boundary evidence，不改 81-case denominator。

36 positive、14 challenge與24 no-action precision的每個first turn都必須以stage-consistent
`ApplicationViewPublication`經`ContextAssembler.get_messages`產生；state card、callable set、blocked reasons
與LocalBackend role boundary皆不可用手組catalog替代。positive fixture另必須真的publish其expected tool。
36-case coverage count不變；`start_training`以可呼叫的`dataset_ready` state取代舊手組`epoch_ready` stage，
所以v9與此前歷史prompt的分數不可直接比較。

- invalid／out-of-stage／stale execution、cancel後continuation與multi-mutation partial action皆為0。
- 36個positive全部得到exact final tool＋parameters，且五個direct preprocess的值都能從latest user
  request驗證；完整值不新增confirmation。
- 五個 missing-parameter cases 的 first raw model response（理想為直接 `respond_to_user` 並指出缺少欄位）
  必須逐 case 完整報告；若模型提出 tool，parameter-origin guard仍必須確保零ApplicationService／ToolExecutor
  execution，但該Host rescue不得回填 raw-model accuracy。
- Clarification gate固定為7條production trajectory：五種direct-preprocess bounded form 證明 user evidence
  收齊後以 receipt 的同一 exact model-selected tool、fresh publication與receipt-reconstructed parameters執行；generic filter先選
  bandpass後才建立typed receipt；bandpass 的 explicit labels、同／跨 reply unlabelled pair collect-then-sort、
  單一 unassigned cutoff 與 correction fail-closed restart 都須在既有兩次 reply budget 內可觀察。取消、無關回答、
  stale generation與不同tool不得使用receipt取得execution authority。這是clarification recovery evidence，
  不回填第一輪raw-model accuracy。
- Raw-model gate只要求 first-generation positive `36/36`。14 challenge、24 precision與7 clarification的raw
  first-generation result仍逐 case 完整報告，包含critical／wording分類，但不得由Host rescue灌成通過，也不以
  `24/24` raw precision或`7/7` raw clarification作本次candidate gate。Host safety gate要求10/10
  direct preprocess value-origin checks；direct Host clarification admission另要求5/5 exact receipts；controller unit/integration另覆蓋cancel、
  topic switch、stale receipt、different tool、partial reply與multi-action。
- Precision gate要求24/24 product outcomes沒有confirmation、GUI handoff、ApplicationService／ToolExecutor
  execution或state mutation。五個缺參數direct tools可由既有parameter-origin guard轉成具體追問；
  out-of-stage的精確requested tool可由既有publication／capability boundary安全阻擋。General、negated、
  ambiguous與multi-action不得以任何substitute tool進入執行路徑。Raw model選擇另行記錄，不冒充產品結果。
- Direct Host clarification admission gate要求5/5 exact direct receipts；product clarification要求7/7 verified
  execution boundary。proven adjacent-complete-object multiple output 的 focused probe 必須是零 execution、零
  confirmation、零 UI handoff。81-case 中所有 no-action row 與上述
  focused probe 的 confirmation、GUI handoff、ApplicationService／ToolExecutor execution或state mutation都使
  product gate fail closed。
- 同一訊息要求多個mutation時一律用`respond_to_user`請使用者選擇第一個要執行的action；本回合不部分
  執行，也不在下一回合自動continuation。
- 真model safe E2E：Switch Dataset、Import GUI、direct Resample。

這些是產品候選gate，不是thesis benchmark或安全零容忍。Thesis evidence另由frozen source、case set、
runner、model revision與至少三次repeat定義；mock、host-assisted guard、dashboard或單次walkthrough
不能宣稱raw-model accuracy。

目前產品在完成migration與同一exact-SHA candidate evidence前，不能宣稱Stable v2、18-tool
runtime、model-free walkthrough或Assistant-ready。
