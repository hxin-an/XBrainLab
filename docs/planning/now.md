# XBrainLab Now

最後更新：`2026-08-18`

## 目前焦點

**建立 Assistant Stable v2 的 durable target authority，之後在暫時 integration branch 以小 PR
完成 replacement、atomic cutover、deletion 與 exact-SHA candidate；在完整候選前不要求使用者手測，
未取得同一 source 的手測通過不得合併 main。**

目前 phase：`Checkpoint；raw→epoch repaired，Granite 2B two-pass rejected`

目前 branch：`refactor/assistant-target-adapters-v2`

已完成：以三個可獨立驗證的local checkpoint完成target migration：A先讓現有Channel Selection
dialog回傳typed terminal；B將舊Host tool-call normalizer刪減成strict identity boundary；C再將runtime與
model projection原子切換成approved 17-tool target，接通七個zero-parameter GUI handoff、五個direct
preprocess、四個lifecycle與`switch_panel`。Local commits依序為`2366c6b3`、`015104ff`、`5da213a3`。

已完成local checkpoint：D1已從`ToolAttemptCoordinator`移除以使用者文字猜command的intent gate；D2已
刪除controller的request admission、product shortcut、Host deterministic continuation與execution snapshot；
D3已移除兩個無production caller的policy modules。保留schema、同generation publication、path provenance、
ApplicationService capability與confirmation；`tests/unit/llm`在target 17 surface上`1680 passed`。

本輪已依序完成兩個slice。第一個slice修復原exact head把「尚無已提交preprocess operation」錯誤
擴大成「產品禁止raw直接epoch」的capability regression：`data_loaded`仍誠實表示只有raw，但同時發布
Channel、五項direct preprocess、Epoch與Switch；`CreateEpoch`要求raw與合法epoch context，不強制先做
preprocessing。可見狀態固定為`EEG data loaded · Ready for preprocessing or epoching`；使用者已明確
授權這項status文案，不授權layout、dialog或theme修改。第二個slice只在evaluator建立同一Granite 2B的
one-pass baseline與model-owned two-pass actionability A/B；未達48/48、相對延遲增幅不超過50%且warm
p95不超過6秒前，不修改產品generation path。不得換模型、恢復Host intent narrowing、降低denominator、
接受partial mutation或以case-specific prompt硬編取得通過。

Raw→epoch repair已在local checkpoint閉合：focused stage／capability，prompt／status、backend／data與Qt
路徑分別通過224、37與3個tests；舊Host「raw後只能preprocess」的recommended-next假設也已
移除。Dataset narrow capture產生36組screenshots，新status文案與backend publication一致；整體
capture仍因與本文案無關的narrow table水平scroll既有gate而為red，不在此slice改layout。
Remote exact-head CI另抓到`test_workflow_projection.py`一個遗漏的同類舊假設：它仍要求
`data_loaded`唯一推薦`preprocess`。Production projection正確回傳無單一recommended command；修正只
更新該test的observable contract，不改production code。

最新 candidate closure 決策與證據：真實 `DataManager.set_loaded_data_list()` 為避免匯入時昂貴複製，
會把raw references放入working `preprocessed_data_list`；`StateSnapshotService`目前卻以該list非空直接將
`active_dataset.has_preprocessed_data`設為true。使用真ApplicationService import重現結果為raw count 1、
preprocessed working count 1、operations空、stage卻為`preprocessed`，違反target的
`Import → data_loaded → Channel或任一preprocess → preprocessed`。正常Granite prompt因此不發布
`select_channels`；no-model debug只驗ApplicationService capability，可繞過stage prompt而掩蓋此defect。
使用者已明確確認修回`data_loaded`，並接受可見status／next action隨正確publication改變；不授權layout、
dialog或theme修改。Montage維持epoch建立後，避免在本slice新增raw geometry persistence owner。

現有34-case Granite gate每個target tool只有兩個固定正向case；沒有target要求的missing-parameter、
cross-stage、general／ambiguous／multi-mutation及lifecycle第三case。原target的「約30–35」與上述最低覆蓋
數學上不相容，使用者已確認改為48：保留34個positive gold cases，另建14個dev-only challenge cases，
同一次model load執行並要求strict 48/48。Challenge不得進production RAG examples，也不得藉Host heuristic、
silent fallback或放寬scorer取得通過。

本repair slice的observable outcome是：import後即使working preprocess list存在，只要沒有已提交operation，
publication仍為`data_loaded`，但backend capability與prompt都允許直接Epoch；Channel或任一preprocess成功後
升為`preprocessed`，直接Epoch則升為`epoch_ready`，Reset後回到`data_loaded`。Backend owner before／after
都是既有StateSnapshotService／ApplicationService；重用既有`preprocessed.operations`、capability policy與
stage projection，不新增owner、state machine、flag、receipt、module或compatibility path。預期觸及
state／capability／stage projection不超過3個production files，淨LOC接近零。若修復需要第二套Assistant-only
readiness、UI layout改動或改寫raw epoch scientific semantics，立即停止。

Granite slice先只改development evaluator與tests。A使用現行one-pass strict envelope；B先輸出internal
actionability gate，再以同一backend publication、同一loaded Granite產生既有final envelope。兩arm每case
最多3次generation，禁止semantic repair、gold leakage、challenge RAG與Host選擇／替換tool。只有B達
48/48、34 positive exact、14 challenge零tool、stage 100%，且符合已鎖延遲門檻，才開始下一個production
slice；否則保留checkpoint並停止。若產品化，預估重用assembler、turn-attempt session、controller、worker
與現有verifier，4–6個production files、淨增約260–600 LOC、owner數不變；超過8個production files、需要
新module／owner或Host semantic label時必須停止並重新做complexity review。

Evaluator-only implementation checkpoint：runner已在同一engine load中交錯執行A與B，並紀錄每pass與
warm p95 latency；B的gate只有`workflow_stage`、`decision`、`reason_class`三鍵，parser不容許
`tool_name`或`parameters`。首次單case真Granite smoke因prompt使用非法JSON union而補出額外鍵，
strict parser正確拒絕；改為合法三鍵skeleton後，同一`import_eeg_data_01`的A、gate與final均
精確通過，A約1.70秒、B約1.78秒。這只是runner與prompt-contract smoke，不是48-case結論。

Exact-source 48-case A/B已在`42300de37d5cadec3329e93b1eccedbe7c29e83f`、固定Granite revision
`707f574c62054322f6b5b04b6d075f0a8f05e0f0`與offline CUDA上完成。A為34/48（positive
34/34、challenge 0/14）；B為22/48（positive 22/34、challenge 0/14）。B有17個gate
format／一致性failure，且多個正確`respond`的gate在final pass仍被模型改成tool call。A warm
p95為1537.94 ms，B為2803.29 ms，約1.823倍；雖低於6秒絕對上限，但超過1.5倍
相對上限。因accuracy與latency兩項都失敗，依stop condition拒絕產品化two-pass；不修改
normal generation path、不恢復Host routing、不換模型，artifact保留於ignored
`build/dev-artifacts/stable-assistant-model-eval/ab-42300de3.json`作development checkpoint。

最新local red-first證據：exact Stable v2 branch可在offline模式載入固定Granite revision並產生strict三欄
JSON，但`inspect_local_assistant_runtime.py --structured-smoke --strict`仍在prompt與oracle中要求已退役的
`query_state`，因而把`{"workflow_stage":"unavailable","tool_name":"query_state","parameters":{}}`
錯判為passed。此結果只證明模型可載入與輸出JSON，不證明target tool-call。修正後`unavailable`階段只接受
backend-published的`switch_panel`及其exact schema；retired、未發布、錯stage或錯參數都必須讓strict CLI
非零結束。若真模型仍選退役工具，該結果視為真accuracy failure，只能調整prompt/schema/approved examples，
不得恢復Host heuristic或compatibility alias。

最新local green證據：修正後runtime inspection以approved target registry、`switch_panel`實際schema及
exact unavailable-stage action作oracle；23個focused tests通過，包含retired tool、錯stage、非法panel與
額外parameter拒絕。固定`ibm-granite/granite-3.3-2b-instruct`在offline、GPU模式載入既有5.07 GB cache，
輸出exact `{"workflow_stage":"unavailable","tool_name":"switch_panel","parameters":{"panel_name":"dataset"}}`
並由`--strict`通過。這只支撐一個真模型target action與strict JSON boundary，不外推17-tool selection accuracy。

Retired-surface deletion checkpoint：已先移除無production caller的Assistant analysis definition／real／mock
wrappers（`evaluate`、`visualize`、`saliency`）及只驗證這三個退役wrapper的測試；backend
`AnalysisCommandService`與Evaluation／Visualization UI owner完全保留。此slice刪除275 production LOC、
新增0、owner before／after不變；focused definitions、mock、assembler與architecture tests通過。

Frozen Granite suite checkpoint：新增從既有34筆target `gold_set.json`與runtime registry派生的bilingual
selection evaluator；每個approved tool正好兩題，prompt暴露對應backend stage的整組target tools，score要求
exact strict envelope、stage、tool、parameters與runtime schema。首次真模型run依目前local setting使用CPU，
600秒內未完成，且舊runner只在全套完成後寫artifact，因而沒有可判讀的partial result。此為evaluator
observability／checkpoint缺口，不是模型accuracy結果；修正為逐case進度與atomic partial artifact，並允許CLI
對本次run明示CUDA但不保存或修改`settings.json`後再重跑。快速單題smoke與candidate 34-case gate維持分級。

Frozen Granite suite green：sandbox內無`/dev/dxg`，因此GPU gate在明確sandbox外本機CUDA環境執行；沒有
修改或保存`settings.json`。第一個GPU run為32/34：一個zero-parameter GUI tool捏造dialog值、一個正確
direct action前置多餘文字；一次negative prompt曾因直接寫出禁用標籤造成30/34，已確認為small-model
priming並移除。最終只保留positive last-position contract（回覆立刻以`{`開始、以`}`結束、zero-parameter
GUI action複製exact empty shape），同一34-case suite達34/34。這支撐fixed Granite revision在frozen
bilingual target set上的raw selection／parameter exactness，不支撐tool execution、GUI完成或thesis-grade
泛化accuracy。

Retired eval deletion checkpoint：舊21-action deterministic／local runners仍import已刪Host classifier且
不可執行，現已由34-case Stable v2 product evaluator取代並物理移除；strict-envelope architecture guard改指
新runner。歷史121-case artifact與dashboard只能作provenance，`docs/validation/thesis_protocol.md`已明確
要求產品surface穩定後重建thesis benchmark，不把34-case產品gate升格為thesis evidence。

Retired showcase red-first：舊`agent_toolcall_showcase`已無法import，且仍把8個舊21-tool案例注入
`product_scenario_manifest`，使產品checkpoint以已退役的`scan_source`、`evaluate`等動作判定Agent成功。
本slice會整包刪除該showcase與runner，從產品scenario manifest移除其execution／validator／8個scenario，
並把剩餘真實data、command-spine、UI與DPI gates明確改為`immediate-12`。Stable v2 Agent本身不塞回這份
通用產品manifest：無模型frontend terminal、34-case真Granite selection與最終人工walkthrough各自保留
單一evidence owner，避免再建立第三份catalog。此slice只刪歷史scripts/tests wiring，不改產品runtime、UI、
ApplicationService或既有產品gate；完成條件是manifest focused tests通過且repo不再import舊showcase。

Retired showcase green：已物理刪除showcase package／entry point共3,472行，產品scenario manifest移除其
execution、validator與8筆自我引用scenario，並將通用checkpoint收斂成不含Agent accuracy claim的
`immediate-12`。Runner summary改用不綁數字的`immediate_profile_passed`，避免下次profile調整再留下
歷史欄位。Manifest focused 16 tests、完整architecture contract合計300 tests、ruff與CLI import smoke
通過；repo除本段歷史說明外不再引用舊showcase。產品runtime、UI與ApplicationService沒有變更。

Retired wrapper cleanup baseline／complexity review：目前runtime已只建立target 17，但dataset整個
definition／real／mock family、training的`set_model/configure_training`、preprocess的standard／channel／
montage／epoch classes仍以compatibility code存在，另有三份只走舊wrapper的integration與一支
`verify_real_tools.py`。它們不是production caller，且其測試會把已退役surface繼續當產品契約；focused
characterization目前330 passed。此cleanup的deletion candidates就是上述wrappers、只驗wrapper的tests與
script；保留五個direct preprocess、start／stop、`WorkflowHandoffTool`、ApplicationService services、
path-provenance core與UI owners。Authoritative owners before／after完全相同，新增0 owner／state machine／
receipt／module／public class；預期3個既有production modules被刪、6個既有production modules收窄，
production淨刪超過1,000 LOC。依family分checkpoint：training→preprocess→dataset；任何仍有非測試caller、
安全path contract被迫刪除或target focused test失敗即停止，不加compatibility shim。

Retired wrapper cleanup green：training只保留start／stop；preprocess只保留五個direct actions；dataset
Assistant definition／real／mock family已整包移除。三份只測舊wrapper的integration與舊
`verify_real_tools.py`一併退役；shared definition／mock tests重寫成exact target contract，path identity、
backend Data Interpretation、ApplicationService與UI tests保留。變更共9個既有production modules，
`+18/-2,386`、net `-2,368` production LOC，依training／preprocess／dataset三個各低於1,500 LOC的
checkpoint提交；owner before／after不變。Focused 442 tests、完整unit collection 11,030 tests、完整
`tests/unit/llm`加no-model debug integration 1,488 tests皆通過；repo不再import已刪dataset／analysis modules。

Candidate gate migration red-first：handoff registry仍把`chatpanel-guided-boundary`、兩支舊training flow、
recovery與long-session列為required；這些腳本明確要求`scan_source`、`query_state`、Host auto-chain與舊
analysis wrappers，和Stable v2 single-action target衝突。不得修成compatibility workflow。Section 4將以
兩個新權威gate取代：`assistant-frontend-contract`透過attested pytest執行三份profile contract與真
MainWindow／AgentManager／Controller／ApplicationService的no-model terminal flow；
`stable-assistant-model-eval`在offline fixed Granite revision、CUDA、34個frozen bilingual cases上要求
strict全通過並保存JSON。既有`granite-runtime`保留作單題load/strict-envelope smoke，RAG gate保留；
舊五個gate與其專用scripts/tests在新gate green後物理刪除。這不改normal UI、模型revision或backend owner。
Frontend replacement gate已以canonical Poetry separator與strict attestation在本機通過（3 passed）；
handoff registry contract 14 tests通過。下一步只刪除已無required gate或production caller的舊capture
entrypoints／driver／evidence tests；共用artifact integrity helper與仍被其他UI evidence使用的程式保留。

舊gate evidence物理清理已完成：guided/training/recovery/long-session的五個entrypoints、專用driver／
runtime／validator與七個專用test files已移除，約刪除12,966行tracked舊證據；visualization仍需的兩個
deterministic training fixture helpers移到單一中性support module，共用source-identity integrity helper保留。
刪除後caller scan為零，相關UI evidence 101 tests通過，完整`tests/unit` collection無error。這不刪
ApplicationService、現行17-tool adapters、normal ChatPanel或任何UI產品行為。
Architecture sweep另發現兩個Assistant-owned controller callback未落在精確allowlist，以及三個本slice
新增的application-surface tests只用generic non-None assertion。已把allowlist校準到實際
`_clear_conversation_presentation`／panel terminal callback，並將tests改為驗證execution kind、capability、
command、publication generation與state；不新增compatibility runtime或改產品行為。Focused 24 tests與
architecture guard自身284 tests通過，完整repository architecture entrypoint仍需在commit後重跑。

Local candidate pre-freeze sweep：完整repository architecture entrypoint通過；完整unit首次為10,871
passed／5 failed，五個failure全在sandbox建立`AF_INET` socket時以`PermissionError`終止，未進產品HTTP
MCP行為；同一HTTP MCP file在允許localhost的本機環境7 passed。全repo Ruff在機械修正一個integration
test import order後通過，Ruff format、Basedpyright（0 errors）與MkDocs strict皆通過。No-model frontend
strict attestation 3 passed，完整debug integration file 5 passed。Source-diverse strict gate在注入既有
D-mounted public fixture root後4/4通過：PhysioNet EDF／BBCI GDF皆完成one-epoch CPU training與safe
artifact reload，EEGLAB SET／MNE CNT完成import-preprocess並在缺乏可靠雙類別語意時fail closed。這些仍是
pre-freeze checkpoint；本段commit後須對final exact head重跑關鍵gate。

Frozen model gate red-first：final GPU gate前確認`run_stable_assistant_model_eval.py`仍直接採用使用者
`settings.json`的model ID與enabled狀態，和gate宣稱的fixed Granite revision衝突；本機protected setting
目前正好是retired model，會使同一source因個人偏好而得到不同結果。最小修正只在eval script建立
ephemeral config：保留現有cache與generation設定，但強制repo-approved default Granite、local backend、
enabled與CLI device；不讀寫或遷移`settings.json`，不改normal runtime。Focused test先以retired user model
重現，要求eval config仍解析成fixed Granite且保留cache path。
Focused red為eval helper不存在；green後ephemeral config固定使用
`ibm-granite/granite-3.3-2b-instruct`，保留使用者cache path、明示CUDA、強制local／enabled且沒有save
call。Stable eval與handoff registry合計19 tests通過；下一步在此修正commit後重跑final exact-source gates。

RAG gate red-first：offline cache、34-point index與repeat initialization皆成功，但known-query oracle仍硬編
已退役`get_dataset_info`，使現行34-case target corpus只能2/3。不得降similarity threshold或恢復舊tool；
將query／request-scope oracle改成approved `import_eeg_data` exact gold prompt，並加source test要求所有
known-query tools都屬於同一`AGENT_ACTION_CONTRACTS.model_tool_names()`。Backend RAG owner、embedding、
index schema與corpus都不變。
Focused red精確抓到retired tool；遷移後RAG／retriever 95 tests通過，真offline MiniLM gate使用既有
D-mounted fixed revision與34-point index達3/3 known queries，request-scoped filter、non-action filter與
repeat initialization全通過。這是最後一個source-side candidate blocker；提交後重新建立final exact SHA。

Remote CI red-first：PR #39 exact head `33129364` 的`linux-integration-agent-timing`在collection時
匯入已物理退役的`ProductTurnPolicy`而失敗；同一檔案沒有被本地`tests/unit`涵蓋。保留原本202-turn
真controller／Qt／history pruning／latency soak，只移除退役import，並將舊「policy instance存在」
assert反轉為「controller不得重新擁有`_product_turn_policy`」。不得為了讓測試collection恢復而復活
Host policy或降低timing gate。該soak另有兩處期待Host把模糊文字攔成clarification buttons；同步改為
每turn經模型回覆、沒有active action且不啟動Application command的Stable v2契約。Focused validation
先重跑該檔，再重跑CI shard mapping與受影響契約。

同一PR head的Linux integration UI與Windows／macOS product lifecycle再共同揭露一個stale跨平台
walkthrough：測試仍等待舊Host產生`Open Data Import` clarification button。Stable v2不再有該Host
中介；將external model boundary固定輸出strict `import_eeg_data` envelope，保留真controller、
AgentManager、MainWindow、typed handoff、chooser cancel與turn correlation，並明確要求不顯示舊action
widget。三個job是同一測試，不建立平台分支或延長timeout掩蓋錯誤。

最新exact PR head `91a325623c8cea26870b6830e50f858638f9609e`的Windows／macOS lifecycle、
Linux UI、unit、backend、controller、debug、IO、pipeline、training、regression、public multi-dataset與
MkDocs皆通過；`linux-integration-rest`只在`tests/integration/agent`的`agent-contracts`子集失敗。
JUnit顯示44個case中27個仍要求已退役的Host blocked-explanation／readmission／continuation、`list_files`、
`scan_source`／preview／recipe、`set_model`與`saliency`Assistant wrappers。這些self-referential舊契約不得
用compatibility alias修綠：保留真正的ApplicationService receipt／TOCTOU／strict-recovery安全語意，改由
現行17-tool或backend command boundary驗證；只證明退役routing的cases直接移除。完成後先跑完整
`tests/integration/agent`與`linux-integration-rest`本地映射，再建立新exact SHA重跑全部remote checks；
任何產品碼或可見UI變更都超出此test-contract slice並停止。

Local green：移除三份只驗退役Host routing的integration檔；產品流只保留strict response、完整回覆
格式拒絕與runtime-disabled可見狀態；strict recovery改用`import_eeg_data`並正確停在pending GUI handoff；
resource receipt只保留目前可達的`start_training`一次性重放、configuration／preflight stale拒絕與blocking
preflight。完整`tests/integration/agent`為40 passed；CI同型`linux-integration-rest`所有九個isolated
subshards通過。Production／UI檔案0變更，owner、state machine與receipt數量不變；本slice為tests/docs
淨刪除，下一步只做static／architecture與exact-head remote CI。

Remote CI在同一head另由`linux-unit-scripts`抓到executable handoff registry仍列出已刪除的RAG
readmission與resource-confirmation test entrypoints。Focused red為
`test_registered_python_entrypoints_exist`精確失敗；security suite應改列保留下來且current可達的
`test_resource_preflight_receipt.py`，不恢復舊Host routing。修正後重跑完整manifest與scripts shard，
再建立新的exact head；其他production／UI scope維持不變。

Registry green：handoff manifest 14 passed，CI同型`linux-unit-scripts`完整1,107 passed；
`assistant-security-suite`現在涵蓋current產品流、lifecycle、202-turn soak、training receipt、strict recovery、
RAG security與worker supervision／timeout，所有entrypoints存在。此修正只改executable validation mapping，
不改gate outcome、產品行為或claim boundary。

已否決的中間路徑：red-first曾將三個target adapters加在舊30-tool runtime旁，立即使runtime變成33，
並被runtime equality／headless contract tests攔截。該狀態不提交；建立第二個過渡catalog會增加遷移
成本且違反single target authority，因此改採一次atomic cutover。

已完成 checkpoint：target authority 已由 PR #34 以 exact merge commit
`7518c7a60ab7e5355b2e5e1fbc6412ba8edeab2b` 合入 main；該 PR 只有 docs/guidance，沒有產品行為。

已完成 checkpoint：CI bootstrap 已由 PR #35 以 exact merge commit
`ddfef059323dbcc14dbcb5ef725deaa4fd071337` 合入 main；19個applicable checks成功，暫時
`integration/assistant-stable-v2` 已從該commit建立。該merge的main push run曾因GitHub runner下載
Actions archive遇到HTTP 429而在setup失敗；同一SHA重跑後Full Test Suite、MkDocs與Pages Deploy皆
completed/success，沒有source-side fix。

已完成 checkpoint：no-generation diagnostic transport 已由 PR #36 以 exact integration merge
commit `54384129c6c6a806f859ff699610855b11628262` 合入`integration/assistant-stable-v2`；normal
Assistant launch不變，debug transport可在不建立或載入Granite時沿用既有controller、ApplicationService
與turn correlation。

已完成 checkpoint：backend setup stage已由PR #37以exact integration merge commit
`2ee0dee90318e0bd68bc6d9f83269d7d271ffb0b`合入`integration/assistant-stable-v2`；
`dataset_ready`現在只在saved split、model與training settings三者皆完成時成立，exact PR head的
Linux full suite、Windows/macOS、public multi-dataset與MkDocs checks皆completed/success。

## 問題與證據

- Stable v2 runtime目前只發布已核准17個actions；舊21-action inventory、showcase、eval與handoff evidence
  已物理退役，不再是current product contract。
- Host intent narrowing、deterministic continuation與多分支response contract已移除；backend publication
  stage、capability、confirmation與schema verifier仍是唯一執行authority。
- Model output現為strict三欄並須acknowledge同一publication stage；debug walkthrough只在真terminal後
  commit下一步，pending dialog／confirmation／navigation期間不consume case。
- 七個GUI handoff（包含Channel Selection typed terminal）皆沿用既有dialog／panel與correlation，沒有
  新增UI workflow owner。
- 真import目前把working preprocess buffer錯認為已完成preprocess，導致正常prompt跳過`data_loaded`與
  `select_channels`；這是交付手測前的產品blocker。
- GitHub已恢復，PR #39既有exact head checks雖全綠，但該evidence沒有覆蓋上述真import→prompt stage
  transition，且產品修正後會失效並須重跑。
- 三份profile目前只有manifest contract與empty-state `contract-failures`自動執行；Complete Workflow、
  Lifecycle／Navigation仍必須由真人完成，不得以gate名稱冒充三份皆已執行。

## Observable outcome

- [Agent target intent ledger](../target/agent.md#target-intent-ledger)是唯一approved target surface，
  current／target不再混用。
- Backend既有stage、publication與capability policy是唯一readiness truth；Host不再自行縮限intent、
  substitute command或自動continuation。
- Import後保持`data_loaded`；只有Channel或任一preprocess成功後才發布`preprocessed`。
- Granite只輸出strict三欄envelope；一個turn最多一個tool或一個response。
- 七個GUI completion tools只開啟既有surface；五個preprocess tools直接走ApplicationService；四個
  lifecycle tools沿用既有confirmation；navigation只由`switch_panel`負責。
- Normal UI layout與dialogs維持穩定；只加入已核准的debug-only banner、progress與Enter gating。
- 最終authoritative owner、workflow state machine與receipt數量不增加，production LOC淨減少。
- 只有完整17-tool、三份no-model profile、真Granite、source-diverse gate與CI在同一SHA閉合後，才
  交付一次完整手測。

## Scope、ordered repair 與 checkpoint

1. **已完成 — Target authority PR → main**：收斂target、decisions、current/target wording與staged
   validation；PR #34 已合入 exact main。
2. **已完成 — CI bootstrap PR → main**：base=`integration/assistant-stable-v2`的product/docs PR會執行
   既有GitHub Actions；PR #35 的完整product／docs checks已通過並合入main。
3. **已完成 — integration branch**：`integration/assistant-stable-v2`已從exact
   `main@ddfef059323dbcc14dbcb5ef725deaa4fd071337`建立；不是產品基線或release source。
4. **已完成 — no-generation diagnostic transport**：PR #36 已合入integration exact
   `54384129c6c6a806f859ff699610855b11628262`；tool-debug session不解析或載入local model，normal
   Assistant launch維持原契約。Exact PR head的CI與Documentation Site皆completed/success。
5. **已完成 — backend setup stage**：`dataset_ready`只代表saved split、model與training settings
   三者全部完成；generated datasets或trainer存在本身不是ready evidence。沿用既有
   `ApplicationStateSnapshot`／`ActiveDatasetSnapshot`／`ActiveTrainingSnapshot`，不新增state owner。
6. **已確認 current baseline — action projection**：prompt、RAG、verifier、eval與showcase目前已從
   `AGENT_ACTION_CONTRACTS.model_tool_names()`取得current catalog；不新增第二份metadata或另開PR。
7. **Local scope-complete／remote pending — strict envelope**：root object exact三欄；stage必須等於backend publication；
   `respond_to_user.parameters` exact只有`message`；格式或stage mismatch走既有bounded repair，禁止執行。
   Exact local commit `a67abe5b`通過完整`linux-unit-rest` 1,312 tests；GitHub服務恢復前不推新remote
   evidence。Minimal state card與one-message context保留到本次獨立slice，避免同時改grammar與內容。
8. **Local scope-complete／remote pending — minimal prompt context**：以一張由同一ApplicationService publication投影的hidden
   state card取代`workflow_decision`、capability map與status payload；prompt history只保留最新一則
   Assistant-visible message，不重播prior user、tool output或action envelope。Controller archival history、
   current Host narrowing與continuation暫時不變。Exact local commit `df0731eb`已完成；GitHub恢復後再建立
   exact-head stacked PR。
9. **已完成 — atomic target cutover**：runtime與model projection一次替換成approved 17；七個GUI
   adapters只回傳trusted command／decision-fields handoff，不執行或保存GUI選擇；Channel Selection接到
   現有dialog並回傳typed terminal。五個preprocess沿用PreprocessCommandService；四個lifecycle沿用現有
   capability／confirmation；navigation仍只由`switch_panel`負責。同一slice停止兩個Host request-admission
   call sites及tool-success continuation，確保一回合一個tool或response。
11. **已完成 — retired surface deletion**：按analysis、dataset protocol／recipe、training wrappers與
    Host policy分片物理刪除obsolete code，不保留compatibility catalog。
12. **已完成 — stage truth repair**：以真load／ApplicationService publication先紅測，將
    `has_preprocessed_data`改由已提交operation判定；同一測試要求normal prompt在import後發布Channel，
    operation後發布Epoch，Reset後回到Channel。依已核准文案只更新既有status presenter，不改
    layout、dialog、theme或interaction；focused state／capture／prompt contract合計196 tests通過。
13. **已完成評估／產品化被拒 — 48-case replacement evidence**：保留34 positive gold cases與
    14個不進RAG的challenge cases。Same-source A為34/48；model-owned two-pass B為22/48，且
    warm p95相對延遲為1.823倍。Accuracy與relative-latency gate均失敗，因此不進入
    production generation slice，不以runtime、frontend或Host fallback掩蓋evaluator failure。
14. **blocked — exact candidate freeze**：current architecture／target count／validation walkthrough已同步；
    完整local handoff與remote applicable checks在同一clean/explained pushed SHA閉合後，才交付正常Granite
    safe E2E與三份真人frontend walkthrough。
15. 手測通過且產品source未變後，以integration→main merge commit合併；之後刪branch並移除暫時CI
    trigger。

每個implementation slice從integration開短branch並PR回integration；CI全綠後squash為一個coherent
commit。Final rollup可以聚合這些已分片審查的commits，但不得加入新的未審實作。

## Scope ceiling 與 UI confirmation

已取得的UI實作確認只涵蓋：

- 既有Assistant經approved GUI tools開啟既有dialog／panel。
- Debug launch的slim banner、step progress、composer提示與pending期間Enter disabled。
- `switch_panel`顯示具體destination，並等待materialized terminal。
- Import後可見workflow status與next action依修正後backend publication由`preprocessed`校準為
  `data_loaded`；不改layout、dialog、theme或interaction structure。

不包含normal product layout、theme、dialog redesign、新generic result card或其他workflow copy變更。
若implementation需要超出以上範圍，停止並重新取得使用者明確確認。

Non-goals：不修改或stage root `settings.json`；不重建ApplicationService；不新增authoritative owner、
state machine、receipt、runtime fallback或第二套compatibility path；不在candidate前啟動thesis-grade
benchmark。

## Focused validation

- Target ledger完整鎖定tool、stage、schema、execution kind、owner、confirmation、terminal與retired
  disposition；其他canonical docs只引用，不複製清單。
- Current architecture必須與exact source一致描述current17 projection；`docs/current.md`仍在合入main前
  保持Assistant尚未正式ready的產品claim。
- Docs link/source audit、guidance audit及MkDocs strict通過。
- 每個code slice加入直接對應的unit／integration evidence；UI handoff驗accepted→completed／cancelled／
  blocked／failed與stale／duplicate。
- Candidate使用同一clean/explained exact SHA完成no-model、Granite、data、UI artifact、static quality與
  GitHub checks；manual acceptance不由automation取代。
- Granite candidate同一次load執行34 positive＋14 challenge並要求48/48；challenge的missing parameters
  必須回`respond_to_user`詢問缺值，cross-stage／general／ambiguous／multi-mutation不得執行partial tool。

目前slice直接證據：

- Stage truth red-first：working raw copy存在但operation history為空時，原source錯誤發布
  `has_preprocessed_data=true`／`preprocessed`；改由既有`preprocessed.operations`判定後，import與reset是
  `data_loaded`，真正operation後才是`preprocessed`。Focused state、Dataset capture、pipeline與prompt
  projection合計196 tests通過；只改已授權status copy，沒有owner、state flag或compatibility path新增。
- 48-case evaluator contract：34個production RAG positive cases保持不變，14個dev-only challenge涵蓋
  missing parameter、out-of-stage、general、ambiguous與multi-action；strict response scorer及positive／
  challenge分組report共8 tests通過。Fixed Granite exact revision
  `707f574c62054322f6b5b04b6d075f0a8f05e0f0`的same-source GPU run完成48 cases：positive 34/34、
  challenge 0/14。Missing-parameter會自行填0.5–45 Hz、50/60 Hz、256/400 Hz、average、z-score；
  out-of-stage會改stage、呼叫替代tool或宣稱未發生的stop/reset；ambiguous會選Channel、multi-action會
  partial執行第一項。兩輪只增加static fallback shape／通用counter-example的prompt實驗最高僅2/14且
  仍含false-completion，已完整撤除，避免為過測試膨脹production prompt。Scorer另加forbidden
  completion claim，防止「已開始／已停止／已reset」文字被required-keyword誤判通過。
  後續model-owned two-pass A/B未改corpus：B只通過22/34 positive且challenge仍0/14；17個
  gate本身格式／一致性失敗，部分正確`respond`的gate也在final被模型改成tool。
  B warm p95 2803.29 ms雖低於6秒，但為A的1.823倍而超過1.5倍上限。本輪已按
  預設stop condition停在evaluator checkpoint。

- Red-first已重現8個focused contract failure：parser接受兩欄root與多分支response，controller不比對
  model/backend stage，prompt與eval仍教舊格式。
- Parser、prompt、controller與local eval現在共用exact三欄；缺stage、額外root key、stage mismatch、
  response額外key均走既有最多兩次bounded repair且不執行。Missing-input field ID只在schema／Host有
  evidence時評分，message-only model response不再自行聲稱欄位。
- 合併驗證`tests/unit/llm`、local eval、runtime inspection與完整agent integration共2,564 passed；
  包含strict recovery、Qt product flow、runtime lifecycle failure、no-model transport與202-turn／兩次
  pruning的長對話。Stage在`empty→data_loaded→empty`間皆使用exact backend token。
- `linux-unit-rest`先以一個仍使用舊兩欄JSON的root contract fixture重現失敗；更新該fixture後完整
  shard 1,312 tests通過，沒有產品source修正。

上一slice complexity review：authoritative owner before／after皆為既有backend publication、controller verifier與
ApplicationService；不新增owner、state machine、receipt、module或public class。Deletion candidates是
多分支response grammar、兩欄root contract與重複response decision copy。實際5個production files
`+116/-153`、net `-37` LOC；不新增owner、module、public class或UI。若需要超過8個production files、
新owner或淨增超過100 LOC即停止拆slice。
Rollback是revert此grammar slice，tool registry、backend command與UI不需migration。

目前slice complexity review：authoritative owner before／after皆是既有ApplicationService publication；
Assembler只做detached projection，不新增owner、state machine、receipt、module或public class。Deletion
candidates是大型`workflow_decision` payload、prompt capability／status payload、多訊息與referential
heuristic。實際1個production file`+84/-84`、net 0；刪除的prompt policy分支由stage-specific card
projection等量取代，owner與prompt authority layers沒有增加。若需要改controller archival history、超過8個
production files、增加owner或pure refactor淨增超過100 LOC即停止拆slice。Rollback只revertprompt
projection，backend state、tool registry、commands與UI不需migration。

目前slice直接證據：red-first重現缺少`state_card`與history上限仍為3；green後card只含exact stage、
generation、可靠性與stage-relevant counts／readiness，unavailable固定三欄，paths、channels、完整settings、
diagnostics、recommendation、capability map與Host decision皆不進prompt。History只投影最新一則可見
Assistant訊息；prior user、tool output與action envelope不重播。`tests/unit/llm` 2,378 passed，最新
assembler／untrusted-context focused 105 passed，完整`tests/integration/agent` 67 passed，ruff與
basedpyright皆通過。

目前cutover complexity review：owner before／after皆為既有ApplicationService command services、
`WorkflowUiHandoffHost`、MainWindow/dialogs與controller correlation；共用zero-parameter adapter與mapped
lifecycle adapter都不是authority，分別服務七個與兩個runtime callers。Deletion candidates是舊30-tool
runtime registration、21-tool model projection、Host request narrowing／continuation，以及後續會物理刪除的
obsolete wrappers。初始working diff共14個production files，因此依stop condition拆成A（1個現有UI file，
只補typed return且不改layout／文案／互動）、B（1個normalizer file，production約淨減798 LOC）與C（其餘
12個production files的atomic public-surface切換）；各checkpoint新增不超過2個共用public adapter classes，
production整體淨減；owner、state machine與receipt皆不增加。若C超過12個production files、增加owner、
需要新dialog或不能沿用既有command terminal即停止。Rollback可依序revert C／B／A；backend services、
既有dialogs與user data不需migration。

## Stop conditions

- Target、current、active plan或source對tool membership／stage／owner互相衝突。
- Prompt、RAG、eval、showcase或walkthrough另存第二份可漂移catalog。
- GUI tool在surface opened時過早回success，或debug在terminal前前進。
- Slice新增owner／state machine／receipt、pure refactor淨增超過100 production LOC，或final
  production LOC非淨減少而未取得complexity exception。
- Granite未達candidate safety／accuracy gate、必要CI有missing／pending／skipped／failed，或
  source在manual acceptance後改變。
- Import後仍非`data_loaded`、normal prompt未發布Channel、operation後未升`preprocessed`，或debug profile
  成功掩蓋normal prompt stage mismatch。
