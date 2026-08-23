# XBrainLab Now

最後更新：`2026-08-24`

## 目前焦點

CI reliability branch 已在 PR #44 的 exact head
`a679f1417649f4266a2af84809684e40b2109293` 完成所有 applicable non-skipped checks，使用者於
`2026-08-21` 回報 Windows 與 Linux 真人手測正常，並以 merge commit
`8d8dcf6030d0b4bd79783b3a086e1efa101d0cd2` 合併至 `main`。

目前主要長期 active slice 是 branch `feature/braindecode-full-catalog-v1`：固定 Braindecode `1.6.1`
的完整模型目錄，以 upstream Braindecode 作正常 provider，將逐檔確認可重散布的模型碼移入
XBrainLab 作 provider unavailable 時才顯示的本地 recovery／legacy catalog，並把現行 13 項的
Model Selection combo 改為可搜尋、可理解 unavailable reason 的完整目錄。

使用者已明確確認：

- upstream 與 legacy 使用不同 stable ID，禁止 silent fallback；
- 所有 upstream model contracts 都可搜尋，不符合目前產品能力者 disabled 並顯示原因；
- legacy 正常時隱藏，只有 upstream provider unavailable 時才顯示；
- legacy source包含逐檔確認的 BSD-3-Clause、MIT、Apache-2.0 code，保留 notices；
- 授權本 slice 使用單一 branch／單一超大型 PR、多個可回退 commit，並對約 `35,000+`
  production LOC 明確例外；所有 commit 完成及 final evidence閉合後才交付一次手測。

Final Model Selection refinement 已取得明確 UI 授權：正常 provider ready banner 是不必要的
資訊噪音；現行 Model parameters 表只涵蓋64個visible contracts中的13個，另外51個只顯示
no-editable-parameters，且文字型別推斷與重新開啟不保留自訂值，不足以作為完整進階設定。
本 refinement 的 observable outcome 是：(1) provider checking期間保留短暫狀態，healthy完成後整列
隱藏，provider unavailable時仍保留local recovery警示；(2)移除Model parameters編輯區，Confirm直接
使用catalog目前的非`None`預設值，保持未手動修改時的既有模型建構語意；(3)`model_params` command、
resource preview、artifact與script contract保持不變；(4)現行disabled／unavailable rows、reason、
dataset-context admission、stable IDs、provider recovery與pretrained-weight行為完全不改。
Scope只包含既有Model Selection widget、直接相關catalog UI metadata、tests、visual artifact與truth sync；
不改Training其他頁面、availability分類／文案、model factory、catalog membership或backend owner。
Owners before／after不變；deletion candidates是QTableWidget參數編輯器、文字parser、empty／resize／selection
helpers；`ModelSpec`的key／default／label metadata仍保留為reviewed default contract，不另做backend
schema refactor。先跑既有selector characterization，再加
healthy-banner-hidden與catalog-default Confirm regressions，完成後跑同一focused suite、Ruff／format、
basedpyright、exact-source default-scale artifact，最後freeze新SHA並只跑一次canonical handoff。
若default model parameters、unavailable行為、provider identity、search／keyboard／Confirm、pretrained
weight或Training command結果改變，立即停止而不以UI簡化為由接受回歸。任何source變更使`a9ca317f`
舊handoff evidence失效；新exact head閉合後才交付Windows／Linux真人手測。

Refinement實作已完成：Model Selection production diff為單一owner file `+21/-179/net -158`，owner數
不變；正常banner與參數表／parser已刪，recovery banner、unavailable rows、search／keyboard、pretrained
weight與backend admission未改。Selector baseline由25 passed收斂為18個observable cases；直接耦合的
catalog／TrainingService／sidebar合計185 passed，capture／DPI script contracts為49 passed。Ruff全repo、
format check、configured basedpyright與MkDocs strict均通過；provisional Xvfb screenshot已人工確認無clipping、
overlap、雙重scroll或舊參數卡高度。下一步只建立focused commit、產生clean exact-source artifact並執行
一次canonical handoff；若失敗只修recorded owner，不為計時重跑。

Exact `b25ee339` 的第一次canonical handoff已按規則在complete-regression停止：8,289個已執行
cases中8,288 passed、1個既有Evaluation lifecycle test失敗；失敗測試在retry render publication到達後
立即斷言worker已由稍後的finished callback釋放，屬observable terminal之前的test race，沒有Model
Selection或產品source failure。修正scope只為該test等待既有`evaluation_background_work_idle` terminal；
不改Evaluation product lifecycle、timeout或UI。先以該node的重複focused執行證明race已收斂，再建立
replacement exact SHA並執行一次replacement canonical handoff；不為計時或成功率重跑舊SHA。

Data Import 與 4B Assistant 模型不在本 slice。

### Parallel slice：Assistant no-action precision

Branch `fix/assistant-no-action-precision-v1` 只處理既有 Assistant 在資訊詢問、否定、模糊、
缺參數、out-of-stage 與 multi-action 請求上錯誤提出 workflow action 的產品體驗。使用者已於
`2026-08-23` 確認：hard gate 以產品最終零誤動作為準；multi-action 必須先詢問要執行哪一項；
保留 frozen 50 cases，另加同一 evaluator 擁有的雙語 precision suite；回覆自然度由同一 SHA
真人手測，不以固定關鍵字冒充語意品質。產品可見 Assistant 回覆行為已取得實作授權；不授權
其他 UI layout、文案或互動 redesign。

Observable outcome：不該執行時只發布正確 response／blocked result，不產生 confirmation、GUI
handoff、`ApplicationService`／`ToolExecutor` execution 或 state mutation；明確、完整、單一 action
仍維持既有 exact tool 與 parameters。Scope 只包含 approved target／validation truth、共用 prompt
policy／assembler、Stable evaluator、直接相關 tests 與 exact-model evidence。Non-goals 是改 18-tool
membership、parser envelope、confirmation、backend capability、controller owner、RAG owner、模型 catalog、
Import 或 thesis accuracy。Owners before／after不變；prompt只表達 approved decision，production
`ToolAttemptCoordinator`／verifier 仍是唯一 admission owner。預估最多兩個 production files且淨增低於
100 LOC；不得新增 module、public class、state machine、semantic Host router或model-specific fallback。

TDD 步驟：先以現行 36 positive 建 passing characterization，再新增 24-case precision product-outcome
scorer並以 pinned 2B 取得 target red；scorer必須重用 production parser／attempt decision，不複製
admission。Treatment A 將 compact decision precedence與精確 no-action envelope放到catalog後方，平衡
目前反覆的action output shapes；若 positive退步則恢復必要shape，若precision仍失敗只再加入四個不複製
case wording的通用contrastive examples。第二個treatment後仍未同時達到36/36 positive、10/10 direct
origin、5/5 missing composed outcome與24/24 precision即停止；不放寬parser、分母或增加Host heuristic。

Focused validation：prompt／parser／attempt coordinator／controller terminal／evaluator unit與integration，
同一clean exact source的offline 2B deterministic report，接著才執行canonical handoff。Windows normal app
手測 capability question、missing bandpass、ambiguous preprocess、out-of-stage training、multi-action、
negated import，以及完整 resample／navigation regression；任何 dialog、confirmation、navigation或mutation
誤觸即失敗。只有 PR current head CI 全綠、使用者對同一 SHA 手測通過並明確批准 merge 後才合併。

`2026-08-23` checkpoint：Treatment A 保持36/36 positive、10/10 direct origin與5/5 missing
composed outcomes，但precision只有12/24。依預先聲明的唯一後續，四個通用contrastive examples的
Treatment B把precision提高至16/24，卻使positive降為32/36、direct origin降為8/10；因此已丟棄B並
回到不回歸既有action的A。兩者都未達24/24 hard gate，predeclared treatments已用盡。本branch不是
handoff candidate，不開PR也不merge；不再加入model-specific prompt、放寬parser／分母或建立Host
semantic router。使用者於`2026-08-23`同意先以隔離的diagnostic組合，讓已下載的Granite 4.0 Micro
3B跑同一74-case gate；本步不修改Settings、product default或其他public contract，結果只作checkpoint，
是否改變PR順序與模型產品定位仍需另行決定。

3B diagnostic結果：`ibm-granite/granite-4.0-micro` exact revision
`56111ae135df9c53a78c99028e7bc24035a9e979`維持36/36 positive、10/10 direct origin與5/5
missing composed outcomes，precision為17/24，優於2B Treatment A的12/24但仍未過24/24。七個失敗是
三個out-of-stage、中文general長回覆被128-token deterministic cap截斷、中文ambiguous，以及中英文
multi-action各輸出兩個相鄰JSON。臨時diagnostic catalog／selector已移除；本結果不批准3B Settings、
product default、PR或merge，也不改變predeclared stop condition。

使用者於`2026-08-23`批准新的兩階段方向，但要求依序取得證據：第一階段先修正evaluator只看單次raw
generation、未走產品最多兩次strict-envelope recovery，且硬切128-token而未對齊產品generation
設定的證據缺口；第二階段才依第一階段結果定稿backend-owned unavailable-action projection。現在只施工
第一階段，不改prompt、tool membership、backend capability、admission、Settings或UI。Observable outcome
是同一50+24分母同時保留first-generation score與完整parser／recovery／attempt／presentation final score，
每次recovery都使用production recovery instructions與原始conversation，並記錄attempt taxonomy、response、
token budget及最終零執行結果；candidate gate以final trajectory為準，raw score只作診斷，不因format retry
或截斷自動通過。假設產品structured-decision token budget就是runtime config的`max_new_tokens`；若source顯示
另有owner則停止校準，不在evaluator另造數值。

第一階段TDD：先加入scripted generation seam，證明第一次format error後使用production policy重試、最多
兩次、最後一個合法envelope才進既有scorer，並證明exhausted、unsafe recovered action及partial report都
fail closed；再移除128-token evaluator override，讓report記錄exact generation policy。Focused validation
只跑evaluator unit、strict recovery production integration、Ruff與同一exact 3B的74-case deterministic
report；人工檢閱24個final visible messages。Stop condition是能區分raw failure、recovered pass、recovery
exhaustion與semantic failure，且frozen core不退步；完成後先回報，不在同一checkpoint實作第二階段。
第二階段仍不得新增readiness owner或semantic Host router，其public projection欄位、blocked reason與
admission語意必須先由第一階段殘餘案例確認。此slice沒有UI修改，因此不需要新增UI確認。

第一階段checkpoint已完成：evaluator schema v6以production `StrictEnvelopeRecoveryPolicy`重建原始
request並最多重試兩次，保留每次response／taxonomy，同時分開`raw_score`與final `score`；structured
generation直接使用production resolver，這次exact 3B為512 tokens、greedy，不再硬切128。Evaluator／
recovery focused suite為135 passed，Ruff與format通過。Exact 3B revision
`56111ae135df9c53a78c99028e7bc24035a9e979`維持36/36 positive、10/10 direct origin、5/5 missing
guard；raw與final precision都是18/24。相較舊17/24，只有原本被128-token截斷的中文general因產品
budget而轉為合法response；兩個multi-action在三次generation都重複輸出兩個相鄰action objects，最後
安全進入`format_recovery_exhausted`，recovery沒有把任何case由fail變pass。其餘四個失敗仍是中文
epochs誤選import、start回覆暗示開始、reset誤選navigation及ambiguous誤選channels。

24個final visible messages已逐一人工檢閱。自動通過只證明沒有confirmation／handoff／execution／
mutation，不能宣稱內容品質：多個out-of-stage回覆改問channels、montage、split ratio、model或training
settings而未說明目前不可用；stop／clear history使用了切換面板或confirmation措辭；saliency改問資料；
中文general含錯字及不存在的visualization模式。這些結果支持第二階段必須投影backend-owned blocked
action與reason，而不是再堆prompt example；也要求第二階段測試同時驗證zero-action與對應blocked reason，
不能只檢查合法`respond_to_user` envelope。下一步先更新approved target／decision，定義非callable、
不授權execution、與callable schemas明確分隔的unavailable-action projection，再以這六個failures及上述
內容誤導案例建立red gate；尚未修改產品projection。

第二階段現已取得使用者`2026-08-23`實作授權並開始。問題證據是exact 3B final precision仍為18/24：
三個out-of-stage案例改呼叫import／navigation或以文字暗示已開始，另有多個自動safe回覆未說明真正
workflow blocker。Observable outcome是模型只看到當下callable schemas，同時能用backend已知的exact
unavailable action與reason回答；被問到未發布action時只`respond_to_user`說明，不提出前置／替代action，
且即使模型輸出該unavailable stable ID，既有attempt boundary也以同一reason、零confirmation／handoff／
execution／mutation fail closed。

Authority與scope：`ApplicationViewPublication`仍是atomic state／capability truth，既有
`build_agent_tool_policy`投影per-tool `ToolAvailability`，`STAGE_CONFIG`仍擁有approved model-facing stage
membership；`ContextAssembler`只做交集與render，`ToolAttemptCoordinator`仍是唯一admission owner。
Callable等於stage target、同一generation backend-enabled policy、registry與target membership的交集。
其餘registered target tools只進獨立non-callable reference：backend-disabled沿用原始public reason；backend
enabled但stage省略者使用bounded「not callable in workflow stage」reason。Enabled但需要confirmation者仍
callable。Non-goals是新增tool／schema／owner／state machine、改capability／confirmation／parser／RAG
owner、建立semantic Host router、修改UI、Settings或model catalog。預估仍只觸及兩個既有production files，
production淨增低於100 LOC；deletion／reuse優先，不新增module或public class。此slice沒有UI修改，既有
Assistant回覆行為授權已涵蓋本次projection，無需額外UI確認。

第二階段TDD／施工順序：先更新approved target／decision；再新增red tests證明同一publication只讀一次、
enabled只出現在callable、disabled只出現在unavailable且沒有schema、原始backend reason與stage-only reason
都綁定同一generation、confirmation-required仍callable、unreliable publication fail closed、RAG只含
callable；接著以既有policy builder填入`PromptPolicyReadResult`，在assembler做交集與reference render，
不複製capability判斷。Boundary test再證明精確unavailable proposal得到`PUBLICATION_BLOCKED`與同一reason，
且不讀execution context、不驗證、不確認或執行。Focused validation跑prompt policy／assembler／RAG／attempt
boundary與直接相關controller integration、Ruff及diff check；之後才以exact Granite 4.0 Micro revision
`56111ae135df9c53a78c99028e7bc24035a9e979`重跑36+14+24並人工檢閱24個final messages。

Stop condition：36/36 positive、10/10 direct origin或5/5 missing guard任一退步就不形成candidate；precision
未達24/24則如實保留checkpoint，不加入model-specific wording、替代執行或Host semantic router。預期本階段
直接處理out-of-stage與誤導blocker回覆，但不宣稱能修正當下確實callable的ambiguous或multi-action格式失敗。
完成focused green與exact-model report後先回報，不開PR、不merge；product行為仍需同一SHA真人手測與明確
merge批准。

第二階段已依stop condition收斂為checkpoint。Precision evaluator現對24 cases建立production
`ApplicationViewPublication`／capability snapshot，prompt與attempt scorer共享同一generation的callable
set／blocked reasons；frozen core仍保留原catalog路徑。Final exact Granite 4.0 Micro report維持36/36
positive、10/10 direct origin、5/5 missing guard；raw precision為19/24、final為20/24。相較第一階段18/24，
start/reset out-of-stage不再進execution，中文general的一次format failure由production recovery安全修正。
四個final failures是中文epochs仍替代呼叫import、中文ambiguous仍呼叫channels，以及雙語multi-action三次
皆輸出兩個JSON後exhaust recovery。

24個final messages已人工檢閱，內容品質仍未通過：Start／Stop／Reset帶有已開始或confirmation語氣，
Channel／Montage／Split／Model／Training Settings多數仍詢問設定值而非說明真正blocker，中文Model列出
產品不存在的模型類型；只有General中文與部分Clear History／Saliency回覆比第一階段清楚。通用「reason是
狀態而非prerequisite命令」規則只在真的有unavailable entries時發布，避免讓frozen positive raw output
退步；它沒有把precision推過20/24，因此不再堆prompt。Final report位於
`/tmp/xbrainlab-no-action-granite-4-micro-3b-phase2-final-v6.json`，SHA-256
`f4b6caf48614ba6899d59e9a0b645b594b01291ba1d8eecbd3006e8c33234de9`；臨時model selector已刪除，
未修改product catalog、Settings或cache。此branch不是candidate，不開PR、不merge；下一步若要處理
callable ambiguous與multi-action，需要另開bounded decision，不能把本checkpoint延伸成Host semantic router。
Focused projection／RAG／attempt／recovery／controller／evaluator suite為194 passed；Ruff check、Ruff format
check與`git diff --check`通過。Precision system prompts實測約7.8–9.6 KB，低於既有request bound；這不是
latency或8,192-token完整壓力證據。`mkdocs build --strict`未執行，因目前Poetry environment未安裝optional
docs group而回報`Command not found: mkdocs`；本checkpoint未為此下載依賴，也不宣稱docs／handoff gate完成。

### Follow-up slice：Assistant clarification continuation

Branch `fix/assistant-clarification-continuation-v1` 從 `6ecc74e9` 的3B／precision checkpoint分出，
只修正使用者已於 `2026-08-24` 手測確認的direct preprocess多輪缺口：第一輪因缺少必要參數而
得到具體追問後，第二輪即使提供答案也被當成新的獨立意圖，因此不會完成原action。現有5/5
missing-parameter evidence只證明模型臆測值被擋下且零execution，沒有證明追問後可恢復；這一差距
在交付前視為blocker。產品可見Assistant多輪行為已取得使用者明確實作授權；本slice不修改Qt layout、
元件文案或其他UI流程。

Observable outcome：五個direct preprocess action在Host因parameter-origin拒絕模型臆測值並提出具體
追問後，使用者下一輪可只回答所缺欄位，模型仍須提出同一個exact action，既有schema、parameter
provenance、current publication／capability與one-action gate全部重驗後才執行。取消、無關回答、
stale publication、new chat、stop或close都不得沿用receipt或執行；另一個完整action只能丟棄舊receipt後
按一般latest-turn admission獨立判斷，不能繼承其provenance。沒有自動continuation，沒有Host選tool，也
不把chat文字解析成authority。

Authority與scope：`PendingInteractionCoordinator`仍是唯一pending interaction owner，新增一個one-shot、
cross-turn typed tool-input receipt，保存exact tool、第一輪user evidence、缺參數追問與prompt-time
publication generation；`ContextAssembler`只投影該bounded receipt，`ToolAttemptCoordinator`／verifier仍
擁有admission與parameter-origin，`ApplicationService`仍擁有current capability與mutation。Receipt只因本次
明確跨turn／TOCTOU boundary而存在，不成為workflow state。Non-goals是新增planner、semantic Host router、
tool membership／schema、confirmation、GUI handoff、backend command、RAG owner、模型catalog或一般長對話
記憶。

Complexity review：deletion／reuse candidates是沿用既有pending clear/reset、`ToolAttemptDecision`、
publication與parameter-origin verification；不擴大raw history、不建立第二份capability、不保留模型臆測
參數，也不新增controller writable alias。Owners before是PendingInteraction（confirmation／handoff）、
ToolAttempt admission、Assembler projection與ApplicationService mutation；after只擴充既有PendingInteraction
的第三種one-shot interaction，owner數不變。預估觸及最多5個既有production files，production約
`+180/-30/net +150 LOC`，不新增module或state machine；新增typed receipt是必要cross-turn identity，
因此在施工前明列此review。若production淨增超過300 LOC、觸及超過8個production files、需要第二個
pending owner或需改model envelope，立即停止並拆成另行批准的public-contract slice。

TDD步驟：先更新approved target／decision，明定clarification receipt不授權execution；再以production
controller入口建立red cases，至少覆蓋resample單欄位回答、bandpass跨輪補值、取消／改題與stale
publication，並斷言真正executor call與exact parameters，而非只看bubble文字。接著擴充既有pending owner、
bounded prompt projection及same-tool provenance evidence，完成最小production修復；最後加入五個direct
preprocess的雙語／代表性兩輪model-eval cases，確認3B能消費receipt，而不把mock green冒充真模型結果。

Focused validation：先跑pending interaction、assembler、parameter-origin、tool-attempt與controller
unit／integration；再跑Stable evaluator與exact Granite 4.0 Micro 3B兩輪clarification report，並重跑既有
36 positive、10 direct-origin、5 missing guard與24 no-action precision，確認安全回歸。Ruff check／format
check與diff check必須通過。只有宣稱可交使用者手測時才執行完整handoff workflow；Windows native仍由
使用者驗收，offscreen或mock不取代。

Stop condition：任一follow-up在缺值、取消、無關回答或stale publication時沿用receipt執行，或receipt替
不同tool提供provenance；既有positive／
origin／missing guard退步；no-action低於目前20/24；receipt跨過new chat／stop／close；或需要解析Assistant
顯示文字才能恢復，都停止而不形成candidate。Scope-complete仍不等於handoff-ready／merge；source固定後
交使用者手測，只有同一SHA明確通過並批准merge才開PR合併。

Implementation checkpoint：既有PendingInteraction owner現保存waiting／active one-shot receipt，Assembler
只在same generation且tool仍callable時投影；ToolAttempt重新執行schema、reply-value provenance與current
capability後才允許exact action。完整Assistant agent／evaluator focused suite為945 passed，Ruff check／format check與
diff check通過；production觸及7個既有files，`+280/-8/net +272 LOC`，未新增owner或module。Pre-freeze
Granite 4.0 Micro 3B v7 run維持36/36 positive、10/10 direct origin、5/5 missing guard與20/24 precision，
五個clarification final為5/5、source receipt皆存在；raw為0/5，四個case經1次、reference經2次既有format
recovery才通過，因此只能宣稱final product-policy continuation，不宣稱第一發JSON紀律改善。下一步是固定
clean exact commit並重跑同一v7 report，再交使用者Windows手測；尚未取得manual acceptance或merge授權。

Exact `fc425eff` 已固定並完成同一v7 report：36/36 positive、10/10 direct origin、5/5 missing guard、
20/24 precision與5/5 clarification final皆維持，完整Assistant agent／evaluator suite仍為945 passed。
使用者於 `2026-08-24` 回報另一個交付前blocker：Assistant composer使用中文IME時，候選組字的Enter
會被誤當成送出；因此clarification候選先不交付，改由下列同一手測候選承接，仍不開PR、不merge。

### Follow-up slice：Assistant Chinese IME composition

Branch `fix/assistant-chinese-ime-v1` 從exact `fc425eff` 疊加，只修正既有
`AssistantComposer` 無條件攔截Enter造成的中文IME組字誤送。使用者已於 `2026-08-24` 明確授權本次
`XBrainLab/ui/` 可見輸入行為修正，並要求完成後與clarification continuation一起交付手測；沒有取得
merge授權。

Observable outcome：IME仍有preedit組字時，Enter不得發出`submit_requested`或建立turn；IME commit後的
中文文字必須留在composer，之後一般Enter才送出一次。既有Shift+Enter換行、英文Enter送出、字數上限、
draft保留、ChatPanel admission與bubble呈現完全不改。Scope只含既有composer owner、直接回歸測試與必要
truth sync；non-goals是版面／文案 redesign、全域event filter、其他輸入元件、Assistant turn lifecycle或
backend修正。

Complexity review：owner before／after皆為既有`AssistantComposer`；沿用Qt的`QInputMethodEvent` preedit／
commit lifecycle與既有key event入口，不新增module、public class、state machine或第二份submit policy。
預估production只改1個既有file、低於30 LOC；若需要全域IME owner、觸及超過2個production files，或必須
改變Enter／Shift+Enter public contract即停止並另行決定。

TDD順序：先用真實Qt input-method event建立red case，證明preedit期間Enter目前會送出；再於composer保存
bounded composition flag，讓已通過platform IME filter的組字Enter不emit也不插入換行，並由
commit／empty-preedit清除狀態。
測試同時證明中文commit內容保留、結束組字後Enter只送出一次，以及既有multiline contract不退步。

Focused validation：以`prlimit --core=0`與timeout執行composer／ChatPanel Qt tests、直接相關chat UI suite、
Ruff check／format check與diff check；固定clean exact commit後，因combined候選source已改變，重跑同一
Granite 3B v7 Assistant report確認clarification與安全分數未退步。Qt offscreen只作engineering evidence；
Windows native手測必須實際用中文IME以Enter選字、確認不提早送出，再驗證一般Enter送出與第二輪補參數。
任何preedit仍送出、commit文字遺失、重複送出、Shift+Enter退步或native IME無法選字皆失敗，不形成
handoff-ready；只有同一SHA經使用者明確手測通過並批准merge後才走PR。

Implementation checkpoint：`AssistantComposer` 現以Qt preedit event保存bounded composition flag；
組字期間抵達widget的Enter會被消費，不emit也不插入換行，commit／empty-preedit event恢復一般Enter。
第一個red證明原實作會emit一次；加強後的red另證明單純呼叫base會產生`"\n中"`，目前兩者皆已由
observable regression關閉。Production只改1個既有file，`+14/-1/net +13 LOC`，owner數不變；完整
chat UI同類suite為233 passed，Ruff check／format check與diff check通過。Exact-source screenshot、
combined v7 model report與Windows native手測仍依上述contract執行；offscreen green不代表中文輸入法
已由真人驗收，也不改變既有20/24 no-action checkpoint。

### Parallel diagnostic：capability-first local model under 4B

使用者於`2026-08-24`澄清4B只是產品預計上限，不是必須填滿的規格；選擇依據是非中國來源、
不超過4B、中文與英文的strict JSON／tool-call能力，以及現有本機資源。第一個新候選固定為
`mistralai/Ministral-3-3B-Instruct-2512-BF16` exact revision
`ecc3ba8b43a45610e709327c049d24b009bfec88`：Mistral AI、Apache-2.0、3.4B language model加
0.4B vision encoder、官方宣稱中文、native function calling與JSON output。這是runtime compatibility
inventory與model-facing evidence，不批准product catalog、Settings、default model或promotion。

Preflight證據：active cache `/home/administrator/.local/share/xbrainlab/models`下載前實測
`11,887,393,909` bytes；候選只允許下載兩個indexed BF16 shards與必要config／tokenizer，排除重複的
`consolidated.safetensors`，exact allow-list為`7,732,474,120` bytes。下載後產品scanner實測候選
`7,732,474,788` bytes、總cache `19,619,868,697` bytes，仍低於原20 GB產品上限。RTX 5070 Ti為
16,303 MiB，preflight時used 1,299 MiB／free 14,697 MiB；不宣稱BF16一定可載入。Repository整包約
15.4 GB且含重複權重，禁止使用無allow-list的現行product downloader。量化不是本次變數；若BF16
無法在資源gate內載入，停止而不silent fallback到4-bit。Cache下載前後都要以產品size scanner驗證，
單模型不得超過10 GB、總cache不得超過20 GB。

使用者於下載期間另授權本次diagnostic最多10 GB額外總cache緩衝，即絕對上限30 GB；這不放寬單模型
10 GB上限，也不授權重複權重、第二個新候選或silent fallback。實際下載未使用這項例外，仍在原20 GB
內，因此後續load／smoke維持較嚴格的現況，不因緩衝額度擴大scope。

Observable outcome：在同一dirty-but-explained Phase 2 source，以evaluator-owned、exact-whitelist、
`trust_remote_code=False`、`local_files_only=True`的`AutoModelForImageTextToText` adapter載入候選；先用
固定一般回覆、明確single action與ambiguous/no-action三個case做不具promotion效力的smoke，再以同一
36 positive＋14 frozen challenge＋24 precision分母跑完整報告。Prompt／backend publication／callable
projection、production parser、最多兩次strict recovery、attempt scorer、512-token greedy policy與GPU
保持不變；只替換model／tokenizer transport。評分停在execution前，不呼叫ApplicationService、
ToolExecutor、GUI handoff或任何產品mutation。

Scope只包含既有Stable evaluator、直接unit tests、必要的exact snapshot下載與`/tmp`報告；不修改
`XBrainLab/llm/core/`、model catalog、downloader、Settings、UI、tool membership、prompt、parser、
admission owner或root `settings.json`。Production `+0/-0/net 0`，owner before／after不變。Evaluator
adapter是受限外部模型seam，不接受任意repo ID、revision、remote code或fallback。UI確認狀態為不適用，
因本diagnostic沒有使用者可見產品修改。

施工順序：先加red tests鎖定exact candidate identity、image-text loader、local-only／no-remote-code與
smoke非promotion語意；再實作最小adapter與CLI candidate selector。Focused green後才以allow-list下載，
先做load＋三case smoke並記錄peak VRAM／format；只有load與smoke都成功才跑完整74 cases。Full gate仍是
36/36 positive、10/10 direct origin、5/5 missing guard與24/24 precision，另人工檢閱24個final messages；
低於此門檻或文字品質不合格都只保留checkpoint。Stop condition是projected／actual cache超限、
`trust_remote_code=False`不能載入、BF16 OOM、任一core gate退步、smoke不能產生可評分envelope，或需要
production backend／model-specific prompt才能繼續；任一發生即停止，不擴大成產品整合或下載另一模型。

使用者於`2026-08-24`批准執行上述diagnostic，並指定收斂決策：Ministral只有在同一74-case gate達到
24/24 precision、36/36 positive、10/10 direct origin、5/5 missing guard，且24個final messages人工
檢閱明顯優於Granite時，才值得另提runtime整合；任何較低結果、只小幅領先或需要額外產品架構都視為
與現行3B差不多，停止Ministral lane並固定`ibm-granite/granite-4.0-micro` exact revision
`56111ae135df9c53a78c99028e7bc24035a9e979`作本次進步版候選。Granite路徑要先收斂Phase 2 diff、閉合
applicable candidate evidence並建立exact handtest source，之後交由使用者真人手測；只有使用者對未再
變更的同一source明確回報手測通過並再次同意merge，才可建立／完成PR merge。自動報告不替代批准。

使用者同日再明確授權：交付真人手測前，獲選模型必須完成Assistant Settings的使用者可見產品整合，
不得要求手改root `settings.json`或以dev evaluator代替產品啟動。這項授權只在model decision後生效；
diagnostic期間仍不把Ministral或Granite臨時加入product catalog。Observable outcome是獲選exact model在
既有單一catalog／download lifecycle／runtime activation spine中顯示正確label與資源資訊，能從Settings
完成選擇、下載或辨識既有完整cache、切換、持久化、重新開啟、啟動與安全刪除，unsupported／incomplete／
OOM或載入失敗仍使用既有fail-closed presentation，且primary default是否改變必須依model結果明確決定，
不silent fallback。Owners before／after不變，不新增第二套readiness、下載、設定或runtime state。

Settings收斂採TDD：先以catalog／config／download lifecycle／dialog／AgentManager現有observable contracts
建立獲選model的red cases，再做最小catalog與既有UI projection接線；focused green後跑真cache inspection、
產品runtime load與一組Assistant turn，並產生exact-source Settings screenshot／walkthrough。若獲選model的
loader與現有product backend不相容，先回報complexity review與最小拆分，不在同一變更偷偷加入平行backend。
任何可見layout、文案、互動或狀態調整已由本段取得明確UI實作授權，但Windows native真人acceptance仍由
使用者對final未變更SHA執行；source再改即撤銷該次批准。

Diagnostic已依stop condition結束。Exact allow-list adapter與report identity的27個focused tests先完成
red→green；但三case smoke在模型配置任何VRAM或generation前即以`KeyError: 'ministral3'` fail closed。
Snapshot宣告`transformers_version: 5.0.0.dev0`，outer `mistral3`內含目前產品Transformers 4.57.6未註冊的
`ministral3` text config；同一exact snapshot的`AutoConfig`在`trust_remote_code=False`重現相同失敗。
`AutoTokenizer`只有在顯式`fix_mistral_regex=True`時可載入，不能證明model runtime相容。Smoke artifact為
`/tmp/xbrainlab-ministral-3b-bf16-smoke.json`，SHA-256
`71ff68c5fc76df9480a92797fc4b4129e65a767fdef069726a5b6aa2a129c9f7`，peak allocated／reserved皆0；
沒有執行74 cases，也沒有模型品質分數。繼續需要升級核心Transformers或不正確改寫architecture，皆超出
本slice，因此Ministral不形成candidate；diagnostic-only adapter／tests要在Settings施工前刪除，避免留下
未被產品使用的runner。已下載cache暫時保留且總量仍低於20 GB，不冒充product-ready model。

依使用者預先指定的收斂規則，本次產品候選固定為`ibm-granite/granite-4.0-micro` exact revision
`56111ae135df9c53a78c99028e7bc24035a9e979`。Assistant Settings要把Granite 4.0 Micro 3B列為新的primary／
recommended default，保留Granite 3.3 2B作lower-memory選項；既有已儲存且仍受支援的2B selection不得被
silent rewrite，新安裝／缺漏／retired selection才解析到3B primary。這是既有單一catalog的membership與
default順序變更，不新增owner；exact revision、Apache-2.0、download／VRAM估計與system-role／dtype contract
都由同一`LocalModelSpec`擁有。先更新approved decision／target，再以catalog、config migration、完整／
incomplete cache、dialog model rows、switch rollback與persistence red cases驅動最小實作。

Handoff直接相依也必須同步：canonical `granite-runtime` gate與開發者真模型walkthrough命令都要指向
同一primary 3B，不得仍以2B通過後冒充primary證據；unit contract先鎖定gate argv中的catalog primary，
再更新executable registry與文件。Settings完成後以真cache inspection、產品`LLMEngine`一個structured
turn、完整74-case report，以及既有Assistant Settings七狀態walkthrough閉合。若24-case precision仍未
達24/24，只能固定為可供比較的checkpoint，不能宣稱`handoff-ready`；是否進入真人產品試用由使用者在
看過四個remaining failures與安全邊界後決定，PR／merge仍等待同一未變更SHA的明確manual acceptance。

Settings development checkpoint已閉合：單一`LOCAL_MODEL_SPECS`現在發布3B recommended primary與2B
lower-memory，retired selection只在UI解析到primary且不改寫stored value，已支援2B selection原樣保留；
現有download／inspection／activate／delete／rollback owner未變。Settings／catalog／runtime／download／
AgentManager focused suite為440 passed；canonical handoff `granite-runtime` argv與developer真模型命令已由
red→green contract同步到3B。Active cache兩個Granite exact revision都回報`gpu-ready`，總量
`19,619,868,697` bytes；3B真產品`LLMEngine`的`general_en` structured turn首輪通過，peak allocated／
reserved為`6,771.76 / 6,872.00 MiB`且close後釋放。既有Assistant Settings七狀態offscreen walkthrough
PASS，ready／advanced畫面已人工檢閱，沒有clipping、horizontal overflow或primary action問題；Windows
native仍未驗收。

同一development source的74-case report為36/36 positive、10/10 direct origin、5/5 missing guard、raw
19/24與final 20/24 precision。四個final failures仍是`epochs_before_data_zh`錯呼叫import、`ambiguous_zh`
錯呼叫channels，以及`multi_en`／`multi_zh`連續三次輸出相鄰JSON而安全exhaust；前兩案仍可能進入GUI
handoff／execution admission，因此不是安全零誤動作候選。暫存報告
`/tmp/xbrainlab-granite-4-micro-3b-settings-convergence.json`的SHA-256為
`dea97c6da73efb5cbb5feee00dd02cad8ebb37acc3857db3d9815ff677dc4079`，但它綁定dirty source，final
checkpoint commit後必須重跑，不能作handoff-ready證據。Settings artifact位於
`/tmp/xbrainlab-assistant-settings-convergence/`；offscreen PASS不取代Windows真人判斷。

Exact checkpoint第一次真`MainWindow → AgentManager → controller thread → Granite → ChatPanel`
walkthrough暴露的是validation drift，不是產品失敗：3B實際成功載入，第一輪約2秒回覆「目前可匯入EEG」且
零tool execution，shutdown／thread cleanup全通過；但舊capture仍要求已退役的`query_state`，因此在正確
no-action response後錯誤fail，並在final payload重新讀persisted Phi selection而覆蓋本次明確`--model 3B`
identity。這兩項直接使full-chain evidence無法判讀，屬本slice內的必要validation修理；不改production、
prompt或UI。先以capture unit tests改鎖兩輪informational request都零tool，並鎖inspected／actual model
identity；再刪除retired query expectation、讓payload使用preflight inspection加controller runtime snapshot。
Focused green後建立replacement commit，重跑74 cases、Settings artifact與真ChatPanel兩輪；任何產品source
行為都不再修改。Root `settings.json`維持使用者既有dirty檔，不stage、不改寫也不拿來作artifact identity。

Validation drift已依上述red→green修正，production `+0/-0/net 0`、owner不變。修正後真ChatPanel兩輪
walkthrough PASS：preflight與controller snapshot都精確為Granite 4.0 Micro 3B；第一輪workflow readiness
回覆約2.0秒、第二輪EEG preprocessing解釋約1.6秒，兩輪都是單句且tool count皆0。Visible screenshots已
人工確認conversation hierarchy、wrapping、composer與空Dataset context無clipping／overlap；post-close
runtime／dispatcher為closed、controller released、registered／running generation threads皆0，GPU也釋放。
Development artifact為`/tmp/xbrainlab-chatpanel-local-fixed/`，JSON SHA-256
`de1b5432b7d828b8765d2ba2dfbe8c25cb8fb36870eaaea6353f12daa4055c40`。這證明真組裝與兩輪資訊回覆循環，
不證明18個GUI action或complete EEG workflow；replacement commit後仍需以新exact SHA重跑並取代本artifact。

施工 checkpoint：catalog／provider chain至`627c5492`已由獨立gate確認無blocker／major；metadata
discovery保持barrel-free，只有checked provider status能啟用projection。`f27eabfa`已鎖定61-symbol逐檔
provenance、hash、license與excluded set。第一個baseline convolution family已完成private namespace、minimal
no-Hub base、逐symbol support provenance與六個model的strict state-dict／deterministic output parity；獨立
gate要求移除未使用的support symbols後已收斂到18個實際primitive，並新增restricted／unrelated source guard。
`861ce481`的複核已PASS。Sleep／temporal family再加入7個models與3個實際support primitives；每個model
已完成upstream strict state-dict／deterministic output parity，兩個代表完成finite backward，且`2fa43d1c`
獨立gate已PASS。Filter-bank family目前加入FBCNet、FBMSNet、FBLightConvNet與IFNet；mixed-license
`filter.py`只摘取BSD的`FilterBankLayer`，未帶入`GeneralizedGaussianFilter`，IFNet另保留MIT notice。
四個model皆完成strict state-dict／deterministic output parity，FBCNet／IFNet完成finite backward；catalog、
provenance與三個family的focused驗證為55 passed，且`09f5482b`獨立gate已PASS。Convolutional／TCN
family目前再加入EEGInceptionMI、EEGITNet、EEGTCNet、EEGSimpleConv、SPARCNet、ContraWR、TSception、
SyncNet、SincShallowNet與SSTDPN；十個model皆完成strict state-dict／deterministic output parity，三個代表
完成finite backward，新增support只限MaxNorm與MaxNormLinear，且`f183d0de`獨立gate已PASS。下一個
bounded family為attention／transformer；STEEGFormer的upstream Hub channel-index下載不會移入legacy，
legacy contract改為使用者顯式提供index或在無channel metadata時沿用identity mapping，禁止網路fallback。
本family現已加入ATCNet、AttentionBaseNet、CTNet、EEGConformer、MEDFormer、MSVTNet、MVPFormer、
PBT、STEEGFormer與TCFormer；10個model皆完成strict state-dict／deterministic output parity，三個代表完成
finite backward。Support closure只新增12個實際attention primitives、PatchTokenizer、FeedForwardBlock、
DropPath、Conv1dWithConstraint與6個直接所需functional symbols；STEEGFormer的Hub lookup已刪除並有
fail-closed regression。六個family加provenance focused suite為58 passed，Ruff／format／basedpyright皆通過，
`c71e5266`的獨立gate指出STEEGFormer仍保留Hub loader surface；`0f1cf3c9`已刪除相關文件、
`_hub_mixin_config`與`from_pretrained`語意，擴充source guard後re-gate PASS。Attention／transformer family
正式關閉。Foundation core／interpolated family目前加入EEGPT、BIOT、BENDR及其三個Interpolated variants；
support closure只新增`InterpolatedModel`與`ChannelInterpolationLayer`所需的6個實際symbols，三個model的
remote loader文件與surface均未移入。六個contracts完成upstream strict state-dict／deterministic output
parity，三個base model完成finite backward；全部既有legacy family加provenance focused suite為68 passed，
Ruff／format／basedpyright皆通過，`61735254`獨立gate已PASS。Foundation leaf family目前再加入
CBraMod、CodeBrain、DGCNN與EEGDINO；support只擴充直接需要的
`CrissCrossTransformerEncoderLayer`與`extract_channel_locations_from_chs_info`，四個model的remote
loader文件與surface均未移入。四個contracts完成upstream strict state-dict／deterministic output parity及
finite backward；全部既有legacy family加provenance focused suite為77 passed，Ruff／format／
basedpyright皆通過，`84d64ff9`獨立gate已PASS。LaBraM／EEGSym family目前再加入Labram、
InterpolatedLaBraM與EEGSym；support只擴充直接需要的MLP、parameter rescale與兩個hemisphere channel
helpers，remote loader文件與surface均未移入。三個contracts完成upstream strict state-dict／deterministic
output parity，Labram／EEGSym完成finite backward；全部既有legacy family加provenance focused suite為
83 passed，Ruff／format／basedpyright皆通過，`8190155d`獨立gate已PASS。SignalJEPA／LUNA family
目前加入SignalJEPA、InterpolatedSignalJEPA、三個classification variants與LUNA；兩個source只依賴
local legacy base／modules，Hub／download文件與可執行loader surface均未移入。六個contracts完成upstream
strict state-dict／deterministic output parity，SignalJEPA／LUNA完成finite backward；全部既有legacy family
加provenance focused suite為92 passed，Ruff／format／basedpyright皆通過，`c0d045b3`獨立gate已PASS。
最後一個REVE family目前已移入其BSD model source，但刪除position-bank HTTP／cache／JSON loader與
remote pretrained surface；legacy forward只接受caller明確提供的`pos`，channel-name lookup在沒有local
position data時fail closed。REVE完成upstream strict state-dict／deterministic output parity與finite backward；
全部既有legacy family加provenance focused suite為96 passed，Ruff／format／basedpyright皆通過，
`fe4b3959`獨立gate已PASS；57個permissive contracts的legacy vendoring正式關閉，四個restricted contracts
只保留metadata。Admission第一個checkpoint目前已建立provider-aware projection：healthy時顯示完整61個
upstream contracts，provider unavailable時改列57個distinct `legacy.braindecode.*` recovery IDs，且explicit
legacy ID在healthy環境仍可解析但不會顯示整份legacy catalog。Catalog factory只傳model宣告的signal context，
Epochs補上detached `chs_info`，TrainingService拒絕disabled contract並把provider／revision寫入ModelHolder；
相關catalog、training service、epochs focused suite為422 passed。下一步是提交本checkpoint並取得同一獨立gate
複核；`0f2d04ac`已關閉legacy alias與舊dialog projection findings，re-gate PASS。Artifact identity checkpoint
目前把exact model ID／provider／source revision寫入ModelHolder、每個新TrainingRecord與saliency producer
fingerprint；同目錄checkpoint／evaluation records因此由training record identity約束，upstream artifact用
legacy identity重開會fail closed，舊artifact缺identity時不會被補寫或冒充某個provider。相關focused suite為
108 passed；malformed identity也會在任何record mutation／evaluation load前以typed error fail closed，
`168dd127`獨立gate已PASS。Model Selection search cutover目前已完成可搜尋result list、name／ID／alias／
family／task filter、disabled reason、no-match、keyboard、selection preservation與provider recovery presentation；
provider true import preflight在Python-owned background thread執行，Matplotlib style side effect由既有lock＋
`rc_context`隔離。Healthy projection顯示61 upstream＋3 local，missing／broken provider顯示57 distinct recovery＋
3 local；找不到原ID時Confirm保持disabled，不替使用者選另一個identity。Catalog＋UI focused suite為52 passed，
focused offscreen screenshot亦已人工檢視。`5cd736a3`的獨立gate發現Enter可繞過hidden／no-match selection；
目前已讓keyboard與`accept()`共用visible＋enabled＋Confirm guard，並以no-match及hidden-selection兩條red→green
regression關閉，UI focused suite為23 passed；`5b6b4016` re-gate已PASS。UI checkpoint正式關閉。下一步進入
全部selectable models的catalog construction／forward與family workflow matrix，不提前執行full handoff。

Model matrix第一輪bounded diagnostic已完成且不重跑：目前static catalog的54個selectable upstream contracts，
在22-channel／512-sample且無montage context有43個產生finite logits；在22-channel／256-sample且有標準10–20
montage context有47個產生finite logits。失敗不是單一factory defect，而是可靜態描述的signal contract：
interpolated／DGCNN／SignalJEPA contextual需要finite electrode positions；SleepStagerBlanco2020與AttnSleep
需要較長sleep windows，AttnSleep另有原始100／125 Hz window contract；Labram需要原始128-channel order及
200-sample patch divisibility，InterpolatedLaBraM需要montage及相同divisibility；LUNA／CBraMod分別需要40／
200-sample patch divisibility；EEGDINO目前最多19 channels。下一個coherent change會在既有ModelCatalog加入
pure dataset-context availability projection，Model Selection只從`controller.get_epoch_data().get_model_args()`
取得detached snapshot，TrainingCommandService在configure時用同一projection重新admit。禁止UI自行推導、
禁止trial construction決定availability、禁止遇到constructor error後fallback。Focused tests要證明各條件的
allow／block、UI reason、UI與command一致及每個enabled contract的bounded construction／finite forward。
目前pure projection與兩個consumer已完成：interpolated／DGCNN／SignalJEPA contextual會要求reviewed finite
positions；SleepStagerBlanco2020要求至少450 samples且預設group-compatible channel count；AttnSleep只接受
single-channel 30-second 100／125 Hz contract，125 Hz由同一adapter固定其documented `d_model=100`；Labram
要求canonical 128-channel order與200-sample divisibility，InterpolatedLaBraM／LUNA／CBraMod分別檢查其
200／40／200 patch contract，EEGDINO限制最多19 channels。Upstream與legacy recovery共用判定；UI只顯示
reason，TrainingCommandService在任何configuration mutation前重新讀Epochs model args並fail closed。三個
focused files目前127 passed，Ruff／format／basedpyright通過。下一步為提交本checkpoint、獨立gate複核，
之後才建立compatible-context construction／finite-forward matrix；不再執行前述兩個diagnostic矩陣。
`a44918a7`獨立gate已PASS。Model matrix下一個slice不新增runner或availability owner：47個一般contract沿用
22-channel／256-sample／standard montage context；七個特殊contract分別使用Blanco 512 samples、AttnSleep
single-channel 3000 samples at 100 Hz、Labram canonical 128-channel／400 samples、InterpolatedLaBraM
22-channel／400 samples、LUNA 22-channel／280 samples、CBraMod 22-channel／400 samples及EEGDINO
19-channel／256 samples。每個static-eligible upstream ID必須由同一catalog projection判為available，以產品
factory與default params產生`(1, 4)`finite logits及至少一個finite gradient；不量scientific accuracy、不以
construction結果回寫availability。Focused evidence是一個獨立integration matrix，任一model失敗即停在該
contract修復，不重跑整個舊diagnostic矩陣。
第一輪完整matrix已一次通過：54個static-eligible upstream IDs全數由產品factory產生`(1, 4)`finite logits
與finite gradient，inventory case合計55 passed／15.25 seconds。Run同時暴露STEEGFormer沒有收到既有
`chs_info`後仍嘗試從Hub下載channel vocabulary並在離線時退回identity mapping；產品從零訓練而不載入
預訓練embedding，因此同一既有adapter明確傳入deterministic local `chan_pos_idx=range(n_chans)`，不新增
optional-input abstraction、不觸發網路、也不假裝具有預訓練montage alignment。以單一factory regression
及該model matrix selector驗證，不重跑54-model matrix。Focused STEEGFormer regression為2 passed／
4.52 seconds，原Hub vocabulary／identity-fallback warning已消失；Ruff／format／basedpyright通過。
`48a031a9`獨立gate已PASS。下一個workflow checkpoint不重跑54-model construction matrix，也不新增
training／artifact／saliency owner：以六個catalog family的代表`EEGNet`（Convolutional）、`EEGConformer`
（Attention）、`FBCNet`（Filter bank）、`BIOT`（Foundation）、`DGCNN`（Graph）及`DeepSleepNet`
（Sleep），在同一真實MNE-backed 22-channel／256-sample兩類Dataset上，各走CPU one epoch。每一case必須
由checked catalog取得factory與exact provider identity、產生selected validation checkpoint、完成test
evaluation、寫出safe record／EvalRecord／model-state artifacts，並用artifact reader strict-load至fresh同ID model。
每一family另只算`Gradient` saliency並驗證finite attribution及producer identity；不跑SmoothGrad family、
不比較scientific metrics。先以EEGNet單一selector打通harness；任何產品contract不相容即停在該family修正，
不把測試改成mock trainer／mock persistence。
Workflow matrix已完成：EEGNet先以單一case通過；其餘family第一次執行時DGCNN正確拒絕只有MNE Info、
但尚未commit到`Epochs.channel_position`的montage，確認是test harness沒有走產品reviewed-montage state而非
model defect。Harness改用`Epochs.set_channels()`正式套用同一standard montage後，六個family整檔一次通過
（6 passed／9.88 seconds）。每例均使用真Trainer、真safe artifact IO、fresh strict-load、test evaluation及
Gradient saliency；未patch persistence或model owner。下一步提交checkpoint並由同一獨立gate複核；不再重跑
此workflow matrix，除非相關training／artifact／saliency source再變。
`e34d2c81`獨立gate已PASS。Platform checkpoint只重用既有`platform-product-lifecycle` registry：Windows
執行54個selectable upstream models的bounded construction／forward／gradient matrix；macOS在同一test module
只執行六個family representatives，Linux authoritative integration仍執行完整54個。這不新增CI job、runner或
timeout，不把macOS best-effort升格為真人desktop claim；focused validation只跑runner contract與本機Linux
collection/cardinality，不在本機重跑model matrix。Registry／Windows-full／macOS-family policy focused
tests為5 passed；Linux collection保留54個model execution cases（另含3個inventory／platform policy cases），
Ruff／format通過，basedpyright只有既有PyYAML source-resolution warning。
`08b39997`獨立gate已PASS。Canonical truth sync更新`current.md`的model-catalog邊界、backend的唯一owner／
artifact identity／legacy license closure、UI的search／provider recovery投影，以及validation的exact-source
Braindecode candidate與Windows手測契約；不新增第二份plan或歷史worklog。MkDocs strict build通過。下一步
提交docs checkpoint，之後freeze product source、產生exact-source Model Selection UI artifact並執行一次
canonical handoff；若任何gate失敗，只修其recorded owner後建立新的candidate，不為計時重跑。
Docs gate指出architecture將identityless legacy stats-only compatibility寫成全面fail closed；實作的正確邊界是
identified／model-backed reopen拒絕缺漏／malformed／mismatch，而current identity同樣unknown時可讀舊statistics
且不可rebind／re-export。只修正該canonical wording後re-gate，不改產品或重跑model tests。
`7d059bff`的第一次canonical handoff在啟動complete regression前由architecture-compliance fail closed：
`ModelSelectionDialog`讀dataset signal context時直接呼叫`controller.get_epoch_data()`，繞過已存在的
ApplicationService command spine。修復只新增一個ApplicationService-owned detached model-signal query，
由既有ApplicationUiRuntime adapter轉交給dialog；不改catalog判定、畫面、搜尋、training mutation或owner數。
Focused validation必須證明product dialog只使用typed runtime query、無runtime時回到metadata-only projection，
並重跑architecture-compliance。建立新frozen SHA後才執行一次replacement canonical handoff；舊SHA的失敗
evidence保留為歷史，不重跑其完整suite。
第一版修復收斂為5個production files、production `+60/-10/net +50`、owner數不變；3個focused behavior
cases、Ruff、basedpyright、MkDocs strict與architecture-compliance均通過。下一步提交並由既有獨立gate
複核；只有新SHA通過後才重建exact-source UI artifact與replacement canonical handoff。
獨立gate指出第一版仍漏接typed product wiring：`TrainingPanel`在typed mode刻意不保留controller，真實
query owner位於既有`_query_port`；只將controller傳入dialog會錯誤退化為metadata-only projection。
修正必須由`TrainingSidebar`把既有TrainingQueryPort顯式注入dialog，helper直接使用該narrow port，並以
真widget＋typed fake port證明context read發生且不相容model被disabled；standalone context才允許fallback。
Typed port wiring已補齊；5個focused cases、Ruff、basedpyright與architecture-compliance通過。第一版
`31f31d1c`尚未push，會以同一focused commit amend後重新取得獨立gate，不保留兩個假候選SHA。
最終修復為6個production files、production `+75/-11/net +64`、owner數不變；`f0a77b80`獨立
re-gate已PASS。
`555ff17f`的replacement canonical handoff在complete regression fail closed。這不是selector evidence
遺失：`linux-unit-backend`有9個由新model identity／channel metadata contract暴露的失真測試fixture，另有
一個cold-import timeout；`linux-unit-rest`的兩個真spawn lifecycle cases在重型54-model backend matrix並行
時未能於既有watchdog內啟動。修復scope只包含：(1)讓saliency、Epochs與ModelHolder fixtures帶有真實
constructor會建立的identity／channel欄位；(2)讓local handoff runner禁止resource-heavy backend group與
spawn-sensitive rest group重疊，但保留八個authoritative Linux groups、unit→integration barrier、coverage與
fail-closed outcome policy。Non-goals是不增加watchdog掩蓋競爭、不刪模型／測試、不改產品行為、CI matrix
或handtest contract。Focused validation為受影響fixture tests、spawn/cold-import cases、runner scheduling
contract、Ruff與architecture guard；通過後建立新frozen SHA，才執行一次新的replacement handoff。若
focused cases仍在隔離狀態失敗、任何test count／coverage policy改變，或排程仍允許兩group重疊即停止。
修復沒有production source變更（production `+0/-0/net 0`，owner數不變）；原9個fixture failures與3個
spawn／cold-import cases均在原watchdog下通過，runner scheduling tests 6 passed，Ruff、format、
basedpyright與architecture-compliance通過。下一步建立單一checkpoint commit並交既有獨立gate複核；
只有PASS後才push並執行新的exact-source replacement handoff。
`0b7d7168`的replacement handoff確認fixture與backend/rest排程問題已關閉，但`linux-unit-rest`仍有5個
runtime-process startup timeout。完整runtime-process test file在獨立process且保留`--cov`時可重現，移除
coverage時原watchdog通過；根因是pytest-cov的`COV_CORE_*`被spawn child繼承，child啟動coverage造成
process-lifecycle probe本身失真。完整core selector進一步證明Downloader的真spawn seam同樣受影響，因此
下一修復只在`tests/unit/llm/core` scoped fixture啟動真child前移除child-only coverage env，
父pytest／其餘group coverage、八group topology與產品timeout不變；先跑完整runtime-process file，再跑
完整`tests/unit/llm/core`的canonical coverage argv。兩者未全通過即停止，不重跑handoff。
Scoped child-coverage isolation完成後，完整runtime-process file在原coverage argv為10 passed，完整
`tests/unit/llm/core`為242 passed；父pytest仍產出coverage且所有原watchdog未變。Ruff、format與diff
check通過，production `+0/-0/net 0`、owner數不變。下一步建立checkpoint並由獨立gate確認沒有coverage／
topology降級；PASS後push並建立新的exact-source candidate。
`0d0eeaaa`的新candidate已使全部unit groups通過，但integration-rest的
`test_saliency_view_publication_lifecycle.py`有16個case在共同fixture建立producer identity時失敗；該fixture
以`object.__new__(TrainRecord)`繞過constructor且漏設`model_identity`，所以尚未進入各自race／cancel／render
assertion。修復只補上同一fixture的`model_holder.catalog_identity`，完整執行該integration file；不改product
saliency或artifact fail-closed規則。若仍有其他failure即停止並按新record分類。
Shared integration fixture補齊後，該file 35 passed，原16個lifecycle cases已跨過producer identity並完成
各自assertions；production `+0/-0/net 0`、owner數不變。下一步做Ruff／diff check、checkpoint與獨立gate，
PASS後才push並重建exact-source evidence。
`cdb222fb`在具備原生CUDA權限的replacement handoff先通過source preflight、Ruff與format，之後由
basedpyright fail closed，尚未進入complete regression。相同gate在sandbox錯誤觀察為0 diagnostics；在
handoff相同原生權限下可穩定重現624個observed diagnostics，其中537個new diagnostics只位於逐檔保留的
`legacy_braindecode`第三方原碼，另7個位於XBrainLab-owned Model Selection Qt Optional access。修復scope
只包含：(1)將exact legacy third-party namespace加入basedpyright exclude，同時保留provenance、model parity、
54-model execution與六family workflow作其authoritative evidence；(2)實際收斂Model Selection的optional
style／list-item access；(3)加入typecheck config contract，防止排除範圍擴張至catalog／adapter／UI。
不更新baseline、不逐行改寫上游vendored演算法、不忽略XBrainLab-owned diagnostics，也不改可見UI行為。
Focused validation須在原生權限下使basedpyright regression為0 new diagnostics，並通過selector、typecheck
contract、Ruff與format；若exclude涵蓋legacy namespace以外、仍有owned-code diagnostics或任何selector
行為改變即停止。通過後建立新SHA並交既有獨立gate，只有PASS才執行replacement canonical handoff。
修復完成後selector＋typecheck contract為29 passed，Ruff／format／diff check通過；原生權限下的
basedpyright regression為80 observed、0 new、1 resolved，沒有更新81筆既有baseline。排除範圍只包含
reviewed legacy third-party namespace與原有LLM model source，catalog／adapter／artifact／UI仍受檢；
production變更為UI null-safe access `+14/-7/net +7`，owner數不變且沒有可見行為改動。下一步建立
checkpoint並由既有獨立gate複核，PASS後push新exact head並執行replacement canonical handoff。
`18d43be4`的replacement handoff已通過source/static、complete regression、Assistant／GPU、UI／native
lifecycle及source-diverse data gates，但在deferred record聚合時由`startup-smoke` fail closed。Artifact顯示
entrypoint在MainWindow前拒絕缺少`XBRAINLAB_CONFIG_DIR`；這是CI reliability已新增的正確產品安全要求，
而local canonical handoff的startup runner仍未提供隔離root。修復只在既有`run_startup_smoke.py` owner內：
未顯式提供root的local probe自建一個含空格與非ASCII的owned temporary root，重用
`build_isolated_environment()`產生全部mutable paths並只注入child；CI顯式root路徑與`run.py` fail-closed
要求保持不變。先讓現有clean-close test對缺少isolated root／environment轉紅，再實作並跑startup unit、
prepare-native contract及一次focused xvfb startup command。若root逃出owned temp、child未收到全部required env、
product設定被寫入真實user path、cleanup掩蓋surviving child或CI explicit-root contract改變即停止。
紅測先以`isolated_root=None`精確失敗；修復後startup＋prepare-native unit contracts為8 passed，包含local
owned-root cleanup與CI explicit-root preservation。原生Xvfb focused smoke實際觀察MainWindow initialized、
Qt `xcb`、close requested、return 0及process-tree quiescent，九個mutable paths全位於含空格與非ASCII的
temporary root；sandbox內同命令因不能連X display而native abort，未被計為產品失敗或pass。修復只觸及
既有dev runner與test，production `+0/-0/net 0`、owner數不變；Ruff／format／diff check通過。下一步建立
checkpoint並由既有獨立gate複核，PASS後push新exact head，再執行replacement canonical handoff。
`735d8a91`的replacement handoff已關閉startup isolation，但complete regression在unit phase fail closed：
`linux-unit-backend`的5,342個cases中只有
`test_policy_import_does_not_cold_start_visualization_stack`失敗，原因是其10秒subprocess probe timeout；
其餘5,341 passed，integration依unit barrier正確未啟動。修復scope只處理這個cold-import test seam：先以
無coverage與handoff相同coverage argv各執行一次，確認產品import contract與`COV_CORE_*` child
instrumentation的差異；若確認，僅讓該probe child不繼承coverage activation，父pytest coverage、10秒
watchdog、`visualization`／`matplotlib.pyplot` absence assertions與產品碼全部保持不變。Non-goals是不提高
timeout、不把import assertion改弱、不改saliency產品行為、runner topology或coverage policy。Focused
validation為同一selector在canonical coverage argv下由red轉green、完整saliency policy file、Ruff／format／
diff check；若無coverage仍timeout、child隔離後assertion失敗，或父coverage artifact消失即停止並按產品import
defect重新分類。通過後建立一個tests/docs-only checkpoint，交既有獨立gate複核並push；之後只執行一次新的
exact-source canonical handoff，不為計時重跑。
Focused red evidence來自`735d8a91` canonical backend shard的10秒timeout；同selector在無coverage時
為1 passed／4.54 seconds，加入父coverage但未隔離child時雖在空載環境通過，整體增至21.61 seconds。
Probe現只移除其child environment的`COV_CORE_*`並反向斷言未繼承；同selector＋coverage為
1 passed／11.97 seconds，完整saliency policy file＋coverage為18 passed／12.19 seconds，父pytest仍產生
coverage artifact。產品source、assertions、watchdog與runner皆未改（production `+0/-0/net 0`，owner數
不變）；Python Ruff／format、MkDocs strict與diff check均通過。下一步建立checkpoint並交既有獨立gate；
PASS後push並只跑一次replacement canonical handoff。
PR #45在exact head `398c4e56`啟動完整remote scope後，Windows product／startup與macOS platform
contracts通過，但required `macos-product-py311`在Training panel（index 2）既有20秒first-open watchdog
fail closed。這不是本branch regression：同一PR base／current main `8d8dcf60`的相同job亦以同一panel 2
timeout失敗。兩份macOS ARM64 log均顯示fresh isolated `MPLCONFIGDIR`在probe期間第一次建立Matplotlib
font cache；main lifecycle step約32秒後於20秒panel budget終止，沒有construction exception或provider
transport failure。修復scope只調整dev／CI evidence contract：Windows仍保留20秒per-panel上限；macOS
product row顯式使用45秒上限，以涵蓋fresh native font-cache cold start且仍bounded，artifact記錄實際budget。
不得retry test、移除macOS job、改成continue-on-error、預熱／共用user cache、改產品／UI，或放寬shutdown、
platform、isolated-root與five-panel assertions。先讓workflow contract對platform-specific budget與CLI wiring轉紅，
再做最小script／workflow修復；focused validation為native smoke unit、CI workflow reliability contract、Ruff／
format／MkDocs／diff check。若macOS exact-head rerun仍timeout、出現materialization exception，或任何其他
non-skipped check失敗即停止按新owner分類。此tests／scripts／CI source變更會使舊local dossier失效；remote
全綠後仍需對final SHA執行一次canonical handoff，才交使用者手測。
Workflow contract先因兩個product rows缺少platform-specific budget而精確轉紅；修復後native smoke與CI
reliability兩個files為19 passed。Windows 20秒與macOS 45秒由finite matrix明列，runner拒絕超過60秒，
CLI forwarding及artifact budget有focused coverage；Ruff／format、MkDocs strict與diff check通過。舊SHA的
其餘所有non-skipped remote checks已completed／success，只有已分類的macOS smoke失敗。下一步建立
tests／scripts／CI checkpoint並交既有獨立gate；PASS後push，等待新exact-head remote CI全綠，再對final
SHA執行一次canonical handoff。
`c0173c49`的macOS native product smoke已在真實ARM64 runner通過，Windows native product／startup、DPI、
product lifecycle、macOS platform、Linux八shard及aggregate也通過；唯一新失敗是Windows
`platform-core-contracts`的model-status background-thread unit test。產品work沒有在GUI thread執行，失敗來自
shared runner的`QThread.start()` admission耗時1.094秒，超過測試歷史上由50ms→150ms→750ms反覆放寬的
wall-clock oracle。修復scope只把cache cleanup與model inspection兩條同型test改為causal synchronization：
release前worker不得完成，Qt heartbeat必須在worker仍blocked時被處理；同步退化會由finite 5秒worker wait
精確失敗。不得提高產品timeout、改lifecycle source、retry pytest、放寬heartbeat／shutdown assertion或改CI
topology。先以舊750ms oracle對1.094秒remote evidence為red，focused執行完整lifecycle test與Windows
platform-core selector contract；Ruff／format／diff check通過後建立新checkpoint交同一獨立gate。PASS後push
並等待新exact-head全綠；因source再變，最後仍只跑一次新SHA canonical handoff，不為計時重跑。

## 問題與證據

- Current catalog只手工發布10個`braindecode.*`模型與3個`xbrainlab.*`本地模型；Braindecode 1.6.1
  自己維護61個model construction contracts。原本QComboBox無法清楚呈現數十個model、task、provider
  與unavailable reason。
- Current factory以`import braindecode.models`載入整個barrel。目錄取得、UI startup與model execution
  沒有分離，barrel也會接觸未選用的model/module和額外import side effects。
- Braindecode 1.6.1 `models/`約33,020 LOC。直接可辨識的source licenses包括BSD-3-Clause、MIT、
  Apache-2.0及至少四個CC BY-NC model；package NOTICE沒有完整列出所有檔案級例外，不能把整個package
  或NOTICE視為單一授權。
- 明確不得移入可發布legacy namespace的model為`EEGMiner`、`MetaNeuromotorHand`、
  `EMG2QwertyNet`、`BrainModule`；`GeneralizedGaussianFilter`另有CC BY-NC與專利
  `GB2609265`聲明。Mixed module只能摘取已確認permissive symbol。
- Braindecode包含一般classification、sleep、foundation／pretrained、interpolated及非classification
  output contracts。Current Trainer預期class logits；「在上游存在」不等於「可由目前supervised
  classification workflow執行」。
- Current`ModelSpec`只表達ID、顯示名、source、factory及少量手工參數；`model_requirements.py`只精確
  描述三個XBrainLab local model。UI、capability、training、checkpoint和saliency尚未共享完整provider／
  task／input／revision contract。

## Observable outcome

1. Catalog以checked-in Braindecode 1.6.1 metadata列出61個model contracts；目錄與搜尋不import
   `braindecode.models` barrel。所有ID唯一，default仍為`braindecode.eegnet`，既有10個upstream ID和
   三個`xbrainlab.*`語意不變。
2. Upstream IDs使用`braindecode.<model>`；本地副本使用`legacy.braindecode.<model>`；既有
   `xbrainlab.*`仍代表原本XBrainLab implementations。Training artifact、checkpoint、evaluation與
   saliency provenance記錄exact model ID、provider及source revision。
3. `ModelSpec`／catalog projection能表達provider、revision、family、task、aliases、license class、
   input requirements、parameter schema、static／dataset-scoped availability及user-safe disabled reason。
4. 每個與current supervised classification workflow相容的upstream model在本slice完成adapter後才可選；
   non-classification、license-restricted、需要未支援modality或external pretrained resource者disabled。
   `adapter not implemented`不是final candidate可接受的disabled reason。
5. Upstream provider正常時Model Selection只顯示upstream catalog。Package不存在、版本不是1.6.1或
   provider preflight失敗時，dialog顯示明確banner並改列可用legacy models；不自動改變已選ID、不執行
   自動fallback。單一model的shape、parameter、checkpoint或training failure必須保留真正typed error。
6. Model Selection使用搜尋欄與可捲動結果列表，支援name、stable ID、alias、family與task；disabled row
   顯示reason且不能Confirm。Keyboard、clear、no-match、cancel、selection preservation、narrow width及
   Windows 100／125／150% DPI均有明確行為。
7. Legacy namespace只含逐檔／逐symbol確認的BSD-3-Clause、MIT、Apache-2.0 closure，保留copyright、
   license notice、Braindecode version、upstream path與hash；不得import installed Braindecode作隱藏依賴，
   不含CC BY-NC／patent code，也不silent下載weights。
8. Final exact head在Windows與Linux完成automated evidence後才交使用者手測；source再變即撤銷批准。

## Scope／non-goals與complexity review

- In scope：model catalog／factory／requirements、training model identity、permissive vendored model closure、
  Model Selection UI、直接必要的checkpoint／evaluation／saliency provenance、tests、CI selectors與canonical
  truth。
- Non-goals：Data Import、4B Assistant model、Trainer task-generalization、非classification trainer、遠端
  pretrained model下載、installer／signing、Braindecode版本升級、scientific accuracy claim。
- User-visible UI modification authorization：已確認。核准範圍只限Model Selection搜尋、result list、
  unavailable state與provider recovery presentation；不重新設計Training其他頁面。
- Owners before／after：`ModelCatalog`仍是唯一model discovery／identity／factory／availability owner；
  `ApplicationService／TrainingCommandService`仍是configure／admission owner；UI只render catalog projection；
  checkpoint／evaluation／saliency各自既有owner不變。Owner count不增加。
- Explicit exception：預估legacy model sources約29k permissive model LOC，加精準support closure、adapters、
  catalog與UI後約`35k–40k`production LOC，遠超normal 1,500 LOC ceiling。使用者核准單一超大型PR；施工仍
  必須以family commits、focused evidence和per-commit rollback控制風險。
- Deletion candidates：現行10-model `_BRAINCDECODE_MODELS`手工tuple、broad barrel factory、QComboBox-only
  selector、依model name token判斷的零散requirements、只為barrel side effect存在的workaround。Braindecode
  dependency保留，因它是primary provider。

## 施工順序

### A. Catalog／license／provider contract

1. 建立exact 1.6.1 model inventory和per-file／per-symbol provenance manifest；61個contracts逐一標記task、
   family、constructor context、license、primary module與產品eligibility。Ambiguous source先blocked，不猜。
2. 先加passing characterization：既有10個ID/default、三個local names、lazy startup、ModelHolder／artifact
   identity及current dialog selection。新增target contract tests需先red於完整membership／search／recovery。
3. 擴充immutable`ModelSpec`和catalog projection；用explicit module/class metadata建upstream factories，
   移除目錄enumeration對barrel import的依賴。Provider preflight只判斷package／exact version／bounded
   provider load，不把model-specific execution error誤判成provider outage。

### B. Legacy permissive closure

1. 建立private legacy namespace與third-party notices。Common base／functional／modules只保留實際model
   callers；mixed-license files按symbol拆分，不copy barrels、Hub publishing、datasets或skorch trainer。
2. 依dependency family分commit移入：baseline convolution、sleep／temporal、filter-bank、inception／TCN、
   attention／transformer、foundation／interpolated。每個commit列新增source、license、direct dependencies、
   parity models與rollback path。
3. Legacy imports只能指向XBrainLab legacy namespace或XBrainLab明確direct dependencies。若Braindecode
   package移除後legacy import失敗，該family不得完成。
4. Restricted models只保留upstream disabled metadata；不得為達membership而移入source。

### C. Admission／artifact與UI

1. 將signal context映射、minimum samples、chs_info／montage、sfreq／n_times、task output與pretrained
   resource requirement集中成catalog-owned pure adapters；UI與TrainingService使用相同結果。
2. Provider與source revision寫入ModelHolder、training plan／record及saliency producer identity。舊
   `braindecode.*` state dict只由同ID upstream factory strict-load；legacy ID沒有silent migration。
3. 以搜尋欄＋result model／list取代combo。Upstream healthy只顯示upstream；provider unavailable時顯示
   recovery banner和legacy results。若current persisted selection本來就是legacy ID，resolver仍可執行，
   但healthy catalog不因此顯示整份legacy list。
4. Selection、search query與provider status不得建立第二份catalog；UI只持有detached projection和目前
   selection。Cancel不mutation；no-match／disabled不能Confirm。

### D. Candidate與merge

1. 每個meaningful commit後只跑family-focused tests，由最多一個獨立subagent gate審architecture／license／
   test evidence；blocker／major以後續commit關閉後才進下一family。
2. 中途不反覆跑complete regression或canonical handoff。所有family、UI、artifact與source guards完成後
   freeze branch，執行一次full handoff、push exact head並等待remote current-head CI。
3. 產生exact-source UI screenshots／walkthrough與Windows操作清單；使用者手測通過並明確同意merge後才
   merge。任何product source改動都使manual acceptance失效。

## Focused validation

- Catalog／provider：既有`test_model_catalog`characterization，加exact 61 membership、unique IDs、default、
  provider version、no barrel enumeration、no silent fallback及provider unavailable projection。
- License／source：provenance manifest completeness、allowed license set、hash/path、legacy self-contained imports，
  banned model／symbol／patent-source absence。
- Model parity：每個selectable upstream model以適當synthetic context執行constructor、forward與finite
  backward；每個legacy model比對upstream 1.6.1 state-dict keys／shapes及deterministic loaded-state output。
  Disabled model只驗證typed reason，不進Trainer。
- Workflow：每個model family至少一條real CPU one-epoch → selected checkpoint → save/reload → evaluation；
  支援gradient的family另驗證saliency。Data semantics仍由既有source-diverse gate擁有。
- UI：search／alias／family、keyboard、clear、no-match、disabled、selection preservation、cancel、healthy／
  unavailable provider、narrow window與default-scale screenshot；Windows跑100／125／150% native DPI。
- Platforms：Linux完整model matrix；Windows執行所有selectable model的bounded construction／forward及native
  selector smoke；macOS執行catalog／import contract和resource-bounded代表family，不宣稱真人desktop。
- Final handtest：正常Braindecode目錄搜尋，EEGNet與至少一個transformer完成CPU training／evaluation／
  Compute Saliency；provider unavailable walkthrough只顯示legacy且不自動換ID；artifact reopen及close／reopen。

## Stop conditions

- 任一copied file／symbol的license或來源不能逐項確認，或完成某model必須帶入CC BY-NC／patent code。
- 需要silent provider fallback、同一stable ID代表不同implementation、第二套model／training／checkpoint owner，
  或UI自行推導availability。
- 任一selectable model不能在其declared input contract下construct／forward，或只能靠未核准remote download。
- Provider preflight會阻塞UI、造成native abort，或legacy仍暗中依賴installed Braindecode。
- Windows model matrix出現unbounded memory／time、native abort或不可重現結果；停止該family並回報，不以
  skip、timeout放寬或降級claim取得green。
- Scope需要擴到non-classification Trainer、Data Import、4B Assistant或installer時停止並取得新決策。
