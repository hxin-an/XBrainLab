# XBrainLab Agent 目標

最後更新：`2026-08-24`

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

| Stage | Backend meaning | Target candidates before capability filtering |
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
直接投影為`epoch_ready`。Montage只在epoch後提供、不改變stage。`start_training` 是 `epoch_ready`
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

符合上述 typed clarification 的 response，或 direct tool 被 parameter-origin guard 擋下時，Host 可以在
零 execution 的具體追問旁建立 typed tool-input receipt。Receipt 只保存 exact tool ID、實際缺少欄位、
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
7. 若存在尚未消費且generation仍相符的direct-preprocess tool-input receipt，加入一筆獨立、host-owned、
   bounded clarification context，指出可由最新回答補齊的exact action；不把它渲染成chat role或callable
   authority。

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
舊 tool output或一般pending intent。唯一例外是上述direct-preprocess bounded clarification receipt；其
tool仍須同時存在於current callable publication，receipt本身不能恢復stale capability。

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

Verification順序固定為：strict schema → backend generation／stage → target publication → parameter
schema → ApplicationService capability → confirmation。Prompt與UI不可成為alternate readiness engine。

Direct-preprocess clarification follow-up仍由模型選擇action，Host不自動continuation。只有模型在 receipt
reply budget 內再次提出同一 exact tool 時，parameter-origin verifier 才可把 receipt 的 verified user
evidence 與最新回答合併；latest-turn explicitly supplied value 永遠優先，Host 只補仍缺 key，並重跑
schema、range、current publication、capability、confirmation 與 one-action checks。模型提出其他 tool／topic、
explicit cancel、stale publication、new chat、stop、close 或第三次 parameter reply 都清除 receipt，零 execution。
同 action 的 parameter-bearing NO_TOOL 或 format failure 只可在剩餘 reply budget 內 requeue；無關回答與
仍缺值不得執行。

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

Evaluator保留第一次未受Host recovery影響的raw score，另將post-recovery score只作diagnostic；candidate
raw-model gate只讀第一次generation。candidate判定仍必須走與產品相同的structured-decision token resolver、
strict parser及最多兩次format recovery；每次response／taxonomy都留在artifact，最後一個accepted或exhausted
presentation outcome才是product score。Format recovery只修envelope，不得把semantic tool-selection failure
重分類為通過。

36 positive、14 challenge與24 no-action precision的每個first turn都必須以stage-consistent
`ApplicationViewPublication`經`ContextAssembler.get_messages`產生；state card、callable set、blocked reasons
與LocalBackend role boundary皆不可用手組catalog替代。positive fixture另必須真的publish其expected tool。
36-case coverage count不變；`start_training`以可呼叫的`dataset_ready` state取代舊手組`epoch_ready` stage，
所以v9與此前歷史prompt的分數不可直接比較。

- invalid／out-of-stage／stale execution、cancel後continuation與multi-mutation partial action皆為0。
- 36個positive全部得到exact final tool＋parameters，且五個direct preprocess的值都能從latest user
  request驗證；完整值不新增confirmation。
- 五個missing-parameter cases必須先由raw model直接`respond_to_user`並指出缺少欄位；若模型提出tool，
  parameter-origin guard仍必須確保零ApplicationService／ToolExecutor execution，但該Host rescue不得回填
  raw-model accuracy。
- Clarification gate固定為7條production trajectory：五種direct-preprocess追問證明只提供所缺值即可讓
  同一exact action在current publication下執行；generic filter先選bandpass後才建立typed receipt；bandpass
  先補low、再補high時只累積可驗證值並重跑完整admission。取消、無關回答、stale generation與不同tool
  不得使用receipt取得execution authority。這是clarification recovery evidence，不回填第一輪raw-model
  accuracy。
- Raw model gate要求36/36 positive、零critical challenge decision failure、24/24 precision no-action與
  7/7 clarification continuation；最多三個noncritical challenge wording failure可以保留並完整揭露。Host
  safety gate另要求10/10 direct preprocess origin checks與5/5 missing-parameter origin blocks，並以controller
  unit/integration evidence覆蓋cancel、topic switch、stale receipt、different tool、partial reply與multi-action。
- Precision gate要求24/24 product outcomes沒有confirmation、GUI handoff、ApplicationService／ToolExecutor
  execution或state mutation。五個缺參數direct tools可由既有parameter-origin guard轉成具體追問；
  out-of-stage的精確requested tool可由既有publication／capability boundary安全阻擋。General、negated、
  ambiguous與multi-action不得以任何substitute tool進入執行路徑。Raw model選擇另行記錄，不冒充產品結果。
- 同一訊息要求多個mutation時一律用`respond_to_user`請使用者選擇第一個要執行的action；本回合不部分
  執行，也不在下一回合自動continuation。
- 真model safe E2E：Switch Dataset、Import GUI、direct Resample。

這些是產品候選gate，不是thesis benchmark或安全零容忍。Thesis evidence另由frozen source、case set、
runner、model revision與至少三次repeat定義；mock、host-assisted guard、dashboard或單次walkthrough
不能宣稱raw-model accuracy。

目前產品在完成migration與同一exact-SHA candidate evidence前，不能宣稱Stable v2、18-tool
runtime、model-free walkthrough或Assistant-ready。
