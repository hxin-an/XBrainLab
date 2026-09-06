# XBrainLab Validation Contract

最後更新：`2026-09-07`

驗證回答「哪個exact source，在什麼環境，觀察到什麼」，不能把單一PASS放大成產品、科學或真人
驗收結論。日常與PR交付按下表選證據；CI routing由既有workflow擁有。明確要求完整dossier時，
gate的ID、順序、argv、timeout與artifact contract仍只以`scripts/dev/handoff_gate_spec.py`為準。

## Daily checks and PR delivery

本機focused checks用於修理回饋；CI負責同一PR head的完整回歸、跨平台與既有artifact gates。
同一證據只執行一次：已有成功的同版本CI artifact時，不在本機重跑等價全套，也不因新增一筆
不相關修改反覆讀取全部圖片。CI未涵蓋的必要證據才補本機執行，命令沿用既有runner。

| 變更 | 本機最小證據 | 交付時必要證據 |
| --- | --- | --- |
| Docs／guidance／config | 結構／設定audit、相關測試，受影響docs build | 同head guidance／docs CI；不跑產品模型評測。 |
| 一般bug／重構 | 可重現defect或passing baseline、相關行為測試與static checks | 同head全部non-skipped CI成功；不另跑本機full regression。 |
| 可見UI | 操作與state測試、changed-surface screenshot／walkthrough | 同head視覺比較；layout／theme／font／dialog變更需Windows DPI gate。 |
| Data／import／label／epoch／training／evaluation／visualization | 對應資料語意與直接lifecycle測試 | 同head canonical source-diverse gate；CI artifact可直接滿足。 |
| Async／native | 完成、取消、stale callback與cleanup的直接保護 | 對應平台CI／stress evidence；未覆蓋的必要native seam才補本機。 |
| Assistant模型／prompt／tool契約／推論流程 | 直接command／policy／trajectory保護 | 適用的真model baseline與GUI journey；其他產品變更不重跑模型評測。 |

大型測試清理保留行為保障的對照，揭露刪除前後數量，不以任意減少denominator冒充品質提升。
Focused檢查通過後，只有新變更、失敗或未解風險才擴大／重跑。同版本CI失敗時先判讀原因；
不以增加timeout、無上限重跑、隱藏skip或忽略失敗來交付。一次重跑通過也保留原失敗的限制。

Git／CI identity、exit code、counts、widget可見／enabled、geometry與pixel差异由deterministic
工具判定。模型審查保留給語意、產品設計與異常原因；不得只看模型敘述就宣稱artifact存在或PASS。
同head CI／artifact連結加focused結果就是一般PR交付證據，不強制另建本機完整dossier。
新source需新CI；不同SHA、環境、模型revision或已知限制的證據不可冒充本次執行。

## Evidence levels

| Level | 支撐 | 不支撐 |
| --- | --- | --- |
| Unit/source guard | Bounded behavior或穩定靜態規則。 | 完整workflow、native UI、real dataset diversity。 |
| Integration | ApplicationService/domain/UI元件間的state transition。 | Windows真人操作或科學品質。 |
| Source-diverse data gate | 代表性來源的import/label/epoch/training contract。 | 所有格式、所有dataset或full BIDS compliance。 |
| Automated UI artifact | Exact-source layout、visible state與interaction；原生Windows capture可證明該DPI的自動geometry檢查。 | 真人DPI／多螢幕操作與usability；offscreen不能代表Windows。 |
| Handoff dossier | 同一clean/explained pushed SHA的完整工程證據。 | 使用者manual acceptance、signed installer或scientific certification。 |
| Manual acceptance | 使用者在指定產品source上完成實際操作並同意merge。 | 未測平台、未測資料集或後續改動的source。 |

## Exact-source requirements

完整dossier至少記錄branch、full commit SHA、HEAD tree、dirty state、protected local paths、source
fingerprint、command、return status、duration、timeout、skips與artifact hashes。只有repo-root
`settings.json`可作為未stage的protected local例外。

不同SHA、dirty source、舊branch、reduced denominator、stale cache或手動加總的結果只能稱
checkpoint。Dashboard是summary，不是dossier。

## Artifact locations

- Development output：ignored `build/dev-artifacts/<family>/`。
- Final handoff：ignored `build/handoff-evidence/<full-SHA>/`。
- Approved visual regression references：`tests/baselines/ui/`。
- `artifacts/`：只保留policy/ignore，不保存current evidence。

UI evidence涵蓋變更涉及的hierarchy、contrast、text fit、primary action、overlap、scroll、geometry與
empty/loading/error/blocked state。主agent實際查看changed surfaces與非預期差異；機械狀態先用
widget／geometry／pixel assertions，同版本未改的畫面不逐張重做模型審查。

Visible UI變更的default-scale candidate必須由`capture_ui_baseline.py`產生exact-source manifest並和
approved references比較；CI不得自行更新reference。Layout、theme、font或dialog路徑另跑Windows Qt
platform的100/125/150% app-polish matrix。Linux/WSL offscreen scale不能冒充Windows結果；automated
Windows capture也不取代真人native DPI、多螢幕或remote-desktop acceptance。

## Explicit full-release dossiers

只有使用者要求完整release dossier、Stable／科學模型能力宣稱，或適用契約明定完整dossier時，
才執行本節。一般產品PR可依上節完成交付；不得把focused／CI交付說成完整manifest通過。

完整 dossier 由 `scripts/dev/run_handoff_validation_manifest.py` 執行；命令、timeout 與 artifact
policy 只讀 `scripts/dev/handoff_gate_spec.py`。Runner 的 `--model-cache-dir` 與
`--rag-cache-dir` 必須指向 D-mounted local caches，寫入 evidence 的 cache paths 必須 redacted。
Evidence root 預設必須是 repo-contained 且 ignored；只有明確傳入
`--allow-external-evidence-root` 才能使用 external root。

完整 runner 會執行所有註冊 sections；只重跑 sections 3-6 或其他子集 does not run or certify
完整 handoff dossier。Windows automated checks 也不取代 Windows native acceptance。

- Identity/scope：Git branch、HEAD/upstream、worktree inventory、dirty ownership與non-goals。
- Focused protection：bug red/green或refactor characterization。
- Same-class sweep：直接相關call sites與必要source guard。
- User-like happy path與相鄰failure/cancel/retry/stale lifecycle。
- Data/import/epoch/training/evaluation/visualization：canonical source-diverse dataset gate。
- Static quality：Ruff、configured Basedpyright、architecture guards、diff check。
- Basedpyright gate以locked analyzer version執行完整project analysis，並和checked-in、唯讀的既有
  diagnostic allowlist比較；resolved diagnostics可單調減少，任何新增diagnostic fail closed。Gate不使用
  Basedpyright會自動改寫的native baseline，也不把sandbox缺少第三方search paths的假綠當證據。
- Docs：canonical truth、link/source audit、developer與user-site strict build。
- Branch/CI：focused commits、pushed exact PR head、所有non-skipped checks completed/success。

本節完整dossier宣稱缺任何required gate時只能稱`checkpoint`或`blocked`。一般PR按上節判定
applicable evidence；同一clean/explained exact commit全部通過才可稱`handoff-ready`。

## Manual merge approval

產品runtime、GUI、資料流程或使用者可見行為有變更時，PR必須記錄`Manual acceptance`：日期、
測試範圍、product source identity與使用者明確的手測通過/merge同意。若product source之後改動，
批准失效並回到checkpoint。CI、自動journey與offscreen screenshot不能取代此批准。

純docs、tests、CI或agent-guidance變更若不可能改變產品行為，可不要求manual acceptance。

### Bounded Assistant baseline merge

本節的真model報告要求適用於Assistant能力／模型契約變更或首次baseline接受。與Assistant無關的
產品PR沿用既有已接受限制，不重跑model評測，也不宣稱該舊model報告是在新SHA上重新產生。
這類無關產品slice可在自身證據完整時稱scoped `handoff-ready`，不代表Assistant promotion。

使用者可明確批准一個尚未達Stable promotion gate、但相對既有main有可驗證進步的bounded Assistant
baseline。這不是可重用的promotion gate：PR必須保存同一exact source的
完整非strict model report、相較既有baseline不得退步的項目、全部known failures與claim boundary，並在
所有applicable non-skipped CI成功後取得同一SHA的Windows真人手測與merge同意。這類source只能稱
bounded baseline或checkpoint，不能稱Stable candidate、promotion或handoff-ready；後續24/24 no-action與
7/7 clarification仍由下列strict gate判定。

`handoff_gate_spec.py`另提供兩個固定、不可任意刪減的manifest profile：預設`handoff`仍使用
`stable-assistant-model-eval --strict`；`desktop-source`只以`bounded-assistant-model-eval
--require-bounded-baseline`替換它，並使用同profile的dashboard。bounded artifact必須綁定primary Granite
exact revision與四份frozen English case files的SHA，完整81/81 inventory、36/36 positive、10/10 explicit
parameter origin、5/5 missing guard，且失敗case只能是PR #71已知的`select_channels_before_data_en`、
`ambiguous_en`、`generic_filter_selection`之一。artifact一律寫`assistant_stable_promotion=false`；profile
不使bounded Assistant成為Stable promotion或完整`handoff-ready`證據。

### Stable Assistant candidate

Assistant candidate必須在同一clean/explained exact source依序閉合下列證據：

1. Unit/integration證明18-tool registry、strict envelope、backend-owned stage、confirmation、GUI
   correlation與no-model diagnostic terminal；mock或manifest-only測試不等於真人workflow。
2. Active Granite English report固定81 cases：36 positive（18 tools各2）、14 challenge、24 no-action precision
   與7 clarification trajectories。Raw model、Host safety、direct Host clarification admission與product outcome
   必須分開報告：Host block、receipt、reconstruction或format recovery只能支持產品安全，不能增加
   first-generation raw-model quality；post-recovery score只作diagnostic。raw-model gate只要求
   first-generation `36/36` positive exact tool＋parameters。14 challenge、24 precision與7 clarification的 raw
   result必須逐 case 如實保留（含critical／wording分類），但不以raw `24/24` precision或raw `7/7`
   clarification作candidate requirement，也不得由Host rescue灌成通過。
   Host safety gate要求10/10 direct preprocess value-origin checks；direct Host clarification admission另要求5/5
   exact direct receipts。Host 不以英文 action／intent grammar 或 import positive-origin rescue 改寫 raw/product
   outcome。product no-action gate要求24/24
   product outcomes沒有confirmation、GUI handoff、ApplicationService／ToolExecutor execution或state mutation；
   product clarification gate要求7/7 final verified execute-boundary。任何no-action product outcome的上述
   side effect都fail closed。
   v12 evaluator必須分開記錄first raw generation、每次production strict-envelope recovery／follow-up raw
   response、Host admission/form transition、receipt-reconstructed parameters與final product outcome；不得直接
   建構receipt、手動塞入pending coordinator或合成parameters。Generation token budget使用production
   structured-decision resolver，不得另設較小的evaluator cap。回覆文字的自然度與完整語意由同一SHA真人驗收，
   不以固定required keyword group作promotion gate。這只支撐bounded selection與production admission outcome，
   不支撐產品ready。
   所有 first-turn family（positive、challenge、precision）的prompt與attempt scorer之callable set／blocked
   reasons必須由同一個production `ApplicationViewPublication`及既有agent capability policy產生；直接使用
   hand-authored stage list或把scorer context中的所有tool設為enabled，不構成state／unavailable-action
   projection證據。36-case tool coverage維持，但`start_training`以最小可呼叫的`dataset_ready` publication
   取代舊的手組`epoch_ready` catalog，故v9不可直接與該歷史路徑的數字比較。
   同一v12 evaluator另固定7個production-controller clarification trajectories：五個direct cases的source
   必須來自precision suite的missing-parameter turn，且第一輪真的由production parameter value-origin boundary
   產生exact tool／question receipt；模型直接`respond_to_user`而沒有Host receipt時不得合成或代填。另外
   generic filter selection、bounded bandpass collect-then-sort與correction fail-closed restart都必須經真controller
   pending lifecycle。所有trajectory仍須經相同parser、schema、publication、capability與attempt policy得到
   7/7 final verified execute-boundary；receipt 收齊後必須零額外 LLM/RAG generation。raw第一發與最多兩次format recovery分開保存。這個gate不取代24/24
   precision，也不等於ToolExecutor已產生真side effect。
3. 真model safe E2E依normal ChatPanel路徑完成Switch Dataset → Import GUI → Select Channels →
   direct Resample；不得用debug transport或fake generator替代。
4. 使用者在同一candidate source完成Complete Workflow、Lifecycle／Navigation、Contract Failures三份
   frontend walkthrough。Import、Channel、Montage、Epoch、Split、Model與Training Settings都必須
   透過真GUI；confirmation/cancel/navigation terminal不可由script預先批准。
5. PR所有applicable non-skipped checks completed/success後，才記錄manual acceptance與merge同意。

### Braindecode catalog candidate

Braindecode catalog／legacy recovery變更在final exact source需閉合下列證據：

1. Catalog／license guard證明61個pinned upstream contracts、54個selectable classification models、57個
   permissive legacy sources、四個CC BY-NC exclusions，以及no-barrel discovery／no-Hub legacy closure。
2. Linux與Windows對54個selectable upstream IDs各執行compatible-context constructor、finite forward及
   finite gradient；macOS至少執行六個catalog family representatives。每個family另有一條real CPU
   one-epoch → selected checkpoint → safe artifact reload → evaluation → Gradient saliency workflow。
3. Exact-source UI artifact顯示searchable healthy catalog。Windows真人驗收再確認：搜尋`EEGNet`與
   `EEGConformer`、disabled reason、no-match／Cancel、100／125／150% DPI；以EEGNet及EEGConformer各走
   CPU one epoch、Evaluation與explicit Compute Saliency。
4. Provider unavailable walkthrough只可顯示distinct `legacy.braindecode.*` recovery IDs，不得自動改變原
   selection；explicit recovery selection完成後的artifact必須記錄legacy provider／revision。恢復provider後
   persisted legacy ID仍不得被rebind成upstream。

此candidate不宣稱scientific accuracy、預訓練權重品質、non-classification task、REVE position-bank支援，
或macOS真人desktop acceptance。

#### Assistant manual walkthrough commands

從repo root啟動，每份profile使用fresh process與fresh session；不加`--model`，diagnostic
transport不建立或載入Granite。JSON profile是executable step sequence authority；本節只保存啟動
方式與人工選擇，不複製call list。

Response Presentation：

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/response-presentation.json
```

Contract Failures：

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/contract-failures.json
```

GUI Cancellation Recovery：

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/gui-cancellation.json
```

Complete Workflow：

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/complete-workflow.json
```

Lifecycle / Routing：

```bash
poetry run python run.py --tool-debug scripts/dev/agent_tool_walkthrough/lifecycle-routing.json
```

開啟XBrainLab Assistant後，每次只送出目前step一次。Dialog、confirmation、navigation或
training尚未terminal時不送出下一步。Unexpected outcome必須留在同一step；記錄step ID、
可見terminal與screenshot後停止，不繼續污染session。

Complete Workflow使用已provision的
`$XBRAINLAB_DATA_DIR/datasets/public-fixtures/physionet-eegmmidb-S008R04.edf`：

- Import以embedded events將T1對應`left fist`、T2對應`right fist`，排除T0。
- Channel Selection套用一組有效EEG subset，至少保留畫面上的C3、Cz與C4。
- Channel與Montage都在Epoch前完成；Montage選當前可用的standard montage，再以EEG Epoch選T1／T2、`0–2` seconds。
- Data Split選Individual／Trial，validation與test皆為`0.2`。
- Model選EEGNet；Training Settings選CPU、1 epoch、batch 8、Adam、learning rate `0.001`。
- 先核准Start Training；若resource preflight另顯示確認，再核准該次receipt，等到training completed。
- 確認Evaluation與Visualization／Saliency Map可開啟；最後核准Compute Saliency，若另有resource
  confirmation則再核准，並等到同一operation顯示`Saliency ready`與腳本`Complete (19/19)`。

任一product source改動都使對應的manual acceptance失效；純docs／tests且不可能改變產品
行為的收尾依本文前述豁免規則處理。

Stage驗收另有一個硬邊界：匯入建立的working raw copy不算preprocessing。只有
`preprocessed.operations`非空（Channel或任一direct preprocess已成功）才可發布`preprocessed`；否則
必須是`data_loaded`並向模型發布Channel與五個direct preprocess工具。

### Staged product rebuild

跨多個bounded slices的產品重建可以先在temporary integration branch組裝，但該branch不是產品
baseline、release source或manual-acceptance對象：

- 每個slice仍需focused evidence、clean/explained source、PR與所有applicable non-skipped checks
  completed/success；integration不能成為較弱CI的避風港。
- Intermediate slice可保留尚未物理刪除但unpublished的migration source；不得同時發布兩套產品
  contract、加入runtime fallback或宣稱handoff-ready。
- Final rollup PR只能聚合已分片審查的commits，不得在rollup新增未審product behavior。其累積diff
  可超過單一slice門檻，但每個原始slice仍受complexity rules約束。
- 使用者只對同步最新main、完整automated evidence已閉合的frozen exact head進行manual
  acceptance。Head或合併基線改變時，必須重新建立candidate並重新取得適用的手測批准。
- Final main merge仍須精確核對base／head、CI及manual acceptance；integration內部成功不能替代。
- 合併後刪除temporary branch與其CI routing；rollback使用PR revert final merge，不保留隱藏雙路徑。

## Claim boundaries

- Format coverage不等於dataset diversity。
- Import成功不等於label semantics、split independence、model quality或saliency validity。
- Cross-fold Summary只對backend證明可pool的disjoint test masks成立。
- Launcher smoke不等於signed installer。
- Local Granite walkthrough不等於Assistant-ready或thesis benchmark。
- Windows真人驗收不能外推macOS、Linux、其他DPI/driver或其他dataset。

歷史執行細節由Git history保存；active狀態只讀[Current](../current.md)與[Now](../planning/now.md)。
