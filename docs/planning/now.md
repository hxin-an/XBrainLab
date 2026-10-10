# XBrainLab Now

最後更新：`2026-10-10`

## Active — 多物件修復未過安全回歸，依核准條件回退並收尾

2026-10-10停止條件已觸發：clean c8057171的9次seeded repair實測，7份B歷史
action＋reply可修成正確action，但2個真雙操作probe均修成第一個action；獨立review
確認這會把原本多JSON零執行終止轉成可准入的部分操作。Seed不是candidate自然首答，
不宣稱自然失敗率；原始9份capture／hash／report全留存。RAG正常、engine／RAG皆已關閉。
依本節既有使用者批准的失敗回退，不再調prompt或加owner：全部production恢復8ff594b0，
多JSON保留直接choose-one零retry／零執行，一般FORMAT_ERROR保留原一次格式修復。
保留有用的測試、scorer錯因修正及模型原始多JSON不得被Host回覆救分的修正；撤掉
僅服務被放棄能力的測試／驗證邏輯。歷史A–D及失敗candidate提交不改写。
回退已完成：production與8ff594b0逐檔相同；直接回退保護8項先red，再product相關281項green，
evaluator兩檔127項green。新增測試保護多JSON出現在首答或一般修復後皆不執行；
保留一般格式修復中的取消／stale回呼保護。沒有新增產品owner或行為。
Next：獨立diff review→clean freeze；只補受影響的舊格式修復實測、
Windows正常ChatPanel與同head CI，再開給使用者集中手測。正常34題產品輸入/raw等價證據
沿用但註明原SHA；不重複跑不受影響的模型推論。累計288/450，禁止因餘額尚有而試新提示。

### 本輪原候選及其驗證（已被上述回退決策取代）

使用者已批准：撤回 R3 提示／catalog／Hz 呈現移植，以原產品 A（8ff594b0）加一次
多 JSON 修復完成回歸、独立覆核、CI、Windows 真實流程與集中手測；未批准 merge。
原 A/B/C/D 證據與提交保留；E/F 診斷不再執行。原研究 checkout／settings／NAS 不動。

- 問題與證據：B→C 首答34份相同，27/34→31/34是修復收益；D剩三題是合法reply漏操作。
  舊positive scorer誤標output_format，須修診斷、不改通過標準或歷史報表。
- Outcome：正常首答的prompt、工具schema與RAG維持A；parser辨識多頂層物件後零副作用，
  提醒模型只回傳一個action或reply。真正多操作要求須reply請選一件，不能選第一個執行。
- Scope：撤回三個產品檔的R3呈現及專屬測試；沿既有policy固定格式提示提醒單一物件，
  不新增session分類狀態或第二提示傳遞鏈；scorer錯因更正、直接測試、文件與既有驗證runner。
  非目標：不改模型、RAG、案例oracle、UI layout、語意重試、跨輪草稿或研究封存。
- Owners不變：既有parser、recovery policy、attempt session、assembler、controller各司其職。
  不新增owner／控制層。Deletion：R3文字renderer、decision reminder及專屬斷言；
  正常產品源碼回復A經apply_patch，不重寫Git歷史。小切片提交、必要時PR revert。
- UI確認：使用者批准無效多物件一次重試、再失敗終止；無layout或工具membership改動。
- 步驟：補red（specific recovery提示、有效reply錯因）→撤回R3／實作→focused green及
  取消／stale／exact-once→獨立實際diff与完整input覆核→clean exact-source模型回歸
  →同head CI／Windows正常ChatPanel→直接開正式Windows版本及log交集中手測。
- 模型驗證：34是回歸非排名；74廣度含真雙操作／缺值／禁止／blocked，26 off配對沿既定
  計畫。保留原34 A對照並核對首答輸入等價；廣度必要時與原A作有界同題比較，不拼接分數。
  既有143次生成；原450硬上限不增加。每次新推論前盤點餘額；不為追分調提示或改題。
- 停止條件：自動與独立覆核無新增阻擋、同head適用CI成功、Windows流程可用後才交手測。
  若新增重試不通過回歸，不追加提示候選或放寬門檻；依使用者批准放棄此新增能力並確認
  原基準可交付。遇需新行為決策或必要環境不可得才明示阻擋，不以checkpoint結束。

已取得red→green：四種malformed→合法重試提醒、合法reply漏操作的scorer分類。
Windows直接controller／policy／assembler／取消與lifecycle 402項、evaluator 80項通過，
changed Python lint與diff check通過。接線重用固定格式提示，無新reason state；正常首答不附。
170份無推論input export（85要求、7 stages），最長2494 tokens；34份正常prompt hash與A全相同。
獨立邊界與完整input覆核無阻擋；校正文案：每次repair刷新publication、各次proposal檢查freshness，
並非跨retry鎖住snapshot。Channel Selection的preprocessed target/source差異為既有advisory，
本輪不擴工具契約。獨立覆核不替代實測。

Clean e2333155真模型34題全部首答通過、raw與A全相同；74廣度獨立tool-decision覆核
65/74首答、66/74最終，仍有既有漏操作／部分複合操作／錯誤替代／不可用工具提案。
原report含兩題回答內容扣分，保留63/64不改寫；4筆錯提案到測試器抑制執行邊界，
不能說是Host擋住。無同期A74配對，不宣稱所有raw全面等價。
RAG off固定26題已完成（27生成），待獨立tool-decision覆核。所有capture verified、engine closed。
累計279/450次生成。自然案例未產生多JSON，另用B的7份既存錯誤與2個固定真雙操作probe
作最多9次單一修復重播（不追加候選），明列seed非本候選自然首答，不混入準確率。
Verifier兩次生成只接受format_error的舊斷言已red→green修正：multiple_objects可通過，
valid/no_tool/未知/缺分類仍不得冒充格式重試；既有gate測試node22項通過。
僅修檢查器，不改模型評分／產品／舊報表；e2333155產品／prompt source保持相同。
Next：凍結final source、9次repair replay、Windows正常ChatPanel、同head CI；
均閉合後直接開Windows正式版與PowerShell log交集中手測。

## Historical — R3 產品移植與有界格式恢復

使用者已批准完整計畫，endpoint 是同版本 CI／獨立覆核／Windows 實機驗證後集中手測，
未授權 merge。產品基準 `8ff594b0647c365f5015579e6e055df566eae0eb`；worktree
`D:\workspace_v2\projects\lab\XBrainLab-assistant-r3`，branch `feat/assistant-r3-recovery`。
原研究 checkout 的未提交文件與 settings.json 不動，NAS／E槽封存與歷史分數不回寫。

### 問題、目標與邊界

研究 Granite4 R3 TEST 的27個錯例已逐題核對，Full的136次生成capture與trace一致。
其中6題是正確操作再附reply object、1題兩個操作、1題尾端fence修復失敗；另有錯誤
不操作、參數、缺值及替代動作。研究R3注入文字工具renderer，而產品仍為JSON catalog，
因此舊研究分數不是本main成績。模型pin、核心工具／RAG相同不等於完整輸入相同。

- Outcome：最新產品底層承接R3提示設計，將multiple JSON納入最多一次格式修復，
  並區分提示移植與修復政策各自的效果。只評tool decision，不追加回答文采評比。
- Scope：規則／工具呈現與必要參數說明、既有parser/recovery接線、直接測試與工程證據。
  單輪英文、一回合一操作、現有18工具、schema/range/source/capability/confirmation不變。
- Non-goals：不搬研究runner、不新增模型／owner／router／semantic retry；不支援歷史補值、
  複合操作或自動前置工作。不調RAG語料、embedding、BM25/RRF參數或評分／題庫答案。
- UI確認：使用者批准多JSON先修復而非立即choose-one的互動變更；無layout重設。
  既有失敗、取消與trusted結果呈現沿用，不把開窗／模型承諾當操作完成。
- Assumptions：重用共享Windows Python與現有固定Granite/RAG cache，離線運作、無下載。
  研究R3來源 `7dea586a:scripts/dev/frozen_dev_contexts/round_03.py.txt` 唯讀參考；
  state/research注入不照搬，必要差異逐项核對。缺環境明示，不silent fallback。

### 步驟與直接驗證

1. 固定20核心＋6英文＋8已知格式案例及oracle，再量A（產品基準）34題。
2. 在現有ContextAssembler／工具定義／prompt policy內移植R3，保留舊retry；
   無第二catalog、無動態研究profile，刪被替代提示。量B同34題。
3. 先寫multiple-object zero-side-effect／one-retry／exhausted失敗測試，再接既有recovery。
   不抽第一個object、不反射錯誤答案作指令、不提供oracle；合法錯工具不semantic retry。
   驗原始要求、publication freshness、confirmation、Stop/New Chat/Restart/Close隔離。
4. 量C同34題，最終74廣度＋26題RAG off配對＋約8真模型GUI流程；沿用產品assembler、
   template、budget與現有工程runner，不建立研究平台。所有首答／retry／raw分開保存。
5. 獨立完整模型輸入覆核（先不看oracle）及recovery/執行邊界覆核，主agent看實際diff／證據。
   applicable同head CI完成成功；Windows正常ChatPanel走Import/Confirm、Channels、
   direct transforms、缺值／禁止／blocked與restart，再開給使用者手測。

Owners前後相同：backend publication/capability、ContextAssembler、既有recovery policy、
turn orchestrator與execution coordinator各守原職；純renderer不是新owner。
Deletion candidates：JSON工具呈現與新文字呈現的重複、舊multiple-object專屬直出分支及
不再成立的專屬測試，保留parser多物件分類與拒絕執行保護。production LOC施工後實算；
觸發repo complexity門檻時先覆核，不以拆檔或增加abstraction掩蓋複雜度。
小commit分別承擔文件／A證據準備、B移植、C恢復；可逐片revert，最後同一PR集中手測。

### 成功、資源與停止條件

- 預計最多210主要請求／420生成，含warmup與少量核對硬上限450次；不是用完配額的目標。
  相同source/input有效證據重用；每次真推論前核對已用數，額度不足先提決策，禁止silent超額。
- 舊TEST8題明列已知回歸，不冒稱新holdout。首答、修復後、Host准入、真副作用分開報；
  Host擋錯不救模型分數。原20題gate不降標、不改oracle，廣度錯誤與退步逐題列出。
- 須證明新修復實測受益，不能用別題加分抵銷新增嚴重誤操作；仍失敗則保留證據，
  不放寬parser或無限提示調優。若需改範圍／預算／驗收條件，明示阻擋並取得決策。
- scope-complete不是handoff-ready；所有applicable同版本gate完成才開正式手測。
  不因compaction、commit、CI pending停工；使用者批准手測後另取得merge同意。
- 收尾按產品、測試/fixtures、scripts、docs、設定/其他分列新增/刪除/淨量與限制。

### 目前進度

固定案例／loader tests 137通過，原提示／工具／context characterization 126通過。
新multi-object政策測試已取得red（舊CHOOSE_ONE不重試），不是環境失敗；原取消／stale
publication保護通過。RAG離線gate通過，重用Windows CUDA／既有cache，未下載模型。
A已在乾淨 `b2dd15508fc90b97df26581a46f3f9f4ba036b3d` 完成，產品與main相同：
34/34首答通過、無repair，34份capture verified、engine closed，RAG30 retrieved／4 empty。
證據 `build/r3-evidence/A/report.json`；這是工程stage fixture，不是研究TEST重現或真人GUI。
34題composite報表刻意不冒充exact20 gate；最終C拆core20／english6／recovery8執行，
總題數不增加。真模型生成已用34／450。單機共用cache已有29.58GB歷史模型，未增下載／刪除。
B移植三個產品檔，production +175/-97/net+78，無新owner；148項直接測試通過。
獨立blind input覆核170份正常/repair完整prompt（85要求、7 stages），1425–2045 tokens，
未見阻擋；repair保留user/state/RAG。這不涵蓋unreliable/error/overflow的實機推論。
保留example照搬及負向要求召回正例的advisory，靠B/C raw與配對證據檢查，不擅調RAG。
B完成於乾淨 `aceab2a5de5634ecab59416a78ae7fe93bce43a3`：27/34首答及最終通過，
7個新增失敗全為正確action後附reply的MULTIPLE_OBJECTS；原core20及english6通過。
34 captures verified、engine closed；這是R3首答退步，不是產品改善。B原始失敗不覆寫。
完整prompt另外以產品實際8192 runtime budget核對，170份bytes/hash與原export完全一致。
真模型生成累計68/450。C接線完成：production +3/-24/net-21，無新owner或提示調整。
直接375項測試中374通過，1項舊B標題斷言遷移後單項通過；runner相關146通過。
腳本不再把多物件偽裝為一般format_error，也不給Host choose-one模型加分。
C獨立邊界覆核無阻擋；乾淨 `cabbb37fb26e3b09a155347445f972291dd24567` 實測：
core20/20、english6/6；recovery8首答1/8，repair後5/8，四題獲救，三題仍多JSON。
合計27/34首答、31/34最終，41次生成，captures verified且engine closed；累計109/450。
不以修復救分掩蓋相對A的退步。目前不符合交付。
依既有驗證契約的一次有界呈現修理，獨立覆核建議移除新加的相鄰完整JSON形狀示例；
D已刪除55 production行，保留R3文字工具／decision steps與所有recovery/parser保護。
先取得wire-only呈現測試red，再224相關測試green；完整170輸入最長1915tokens。
D獨立覆核確認170輸入只刪示例，user/state/RAG/repair原文不變。
乾淨 `2f7e0e52` 完成所有34題：core20/20、english6/6、recovery5/8，首答與最終均31/34。
三個失敗為TEST-A02-01-V0、A02-01-V1、A04-02-V1：合法respond_to_user承諾開窗，
卻未呼叫select_channels/create_epochs；是語意漏操作，不是可重試的格式错误。
歷史positive scorer將NO_TOOL標作output_format，其raw/parser事實不能因此混為格式修復。
34份實際prompt hash符合獨立review export；案例/oracle與A相同、capture verified、
engine closed、source clean。D消除多JSON但未消除R3移植退步，不能宣稱改善或交付。
真模型累計143/450；尚未跑74廣度、26 off配對、Windows native、CI或開PR。

### Historical — 先分析錯誤，診斷比較未開跑（由上方收尾決策取代）

唯一有界呈現修理已用完，候選仍比A少3題。不能沿用舊Development例外或調低門檻
直接交手測，也不因額度尚有剩餘繼續試prompt。所有A/B/C/D成功與失敗證據留在
`build/r3-evidence/`，對應source以各report擁有，不改歷史研究結果。
使用者要求先分析錯誤再決定下一輪，已同意此順序。退回原產品prompt加新recovery只是
保守候選，不是已選定方案。本步只核對現有source/capture與整理文件，不改產品或追加推論。
已知Assistant偶發匯入卡住根因未證實，Restart只是恢復入口；不宣稱本輪修好。

#### 逐題事實與證據限制

下表只列固定34題中的8個已知回歸；其餘26題在A/B/C/D都首答通過。A/B欄為首答，
C/D欄為最多一次修復後結果。通過指工具與參數選擇，非回答文采或真GUI完成。

| 案例（TEST-前綴省略） | A | B | C | D |
| --- | --- | --- | --- | --- |
| A02-01-V0：開channel selector，之後選C3/C4 | 通過 | 雙JSON | 雙JSON | 回答代替操作 |
| A02-01-V1：開channel selection，由使用者設定 | 通過 | 雙JSON | 通過 | 回答代替操作 |
| A02-02-V1：開channel window，之後選較小集合 | 通過 | 雙JSON | 雙JSON | 通過 |
| A03-01-V1：開montage供檢視，尚不套用 | 通過 | 雙JSON | 通過 | 通過 |
| A04-02-V1：開epoch settings供檢視 | 通過 | 雙JSON | 通過 | 回答代替操作 |
| A12-02-V0：執行min-max | 通過 | 通過 | 通過 | 通過 |
| A15-02-V0：清除既有preprocessing | 通過 | 雙JSON | 通過 | 通過 |
| A15-02-V1：reset後使用者再試其他流程 | 通過 | 雙JSON | 雙JSON | 通過 |

- C→D最終同為31/34，但修好A02-02-V1/A15-02-V1、退步A02-01-V1/A04-02-V1；
  不能只看相同總分，或把目前三題當成始終未修好的同三題。
- B→C首答保持相同，格式repair救回四題；C→D僅移除system完整輸出示例，雙JSON在
  本34題中消失，但部分操作改為合法reply。這支持示例影響此批輸出，不證明模型內部機制。
- D三個漏操作的工具均callable、零參數。兩個channel案例RAG為正常empty（非error），
  epoch案例已有create_epochs_01/02兩個正確開窗示例仍失敗。RAG內容各版保持一致，
  不能直接歸因RAG不足；這也不能證明RAG永遠無影響。
- 三題輸入分別1524/1519/1693 tokens，未觸及8192 runtime bound；實際prompt/raw hash、
  題目/oracle、model revision與生成設定已對照。沒有發現截斷、漏工具或source混用。
- 合法NO_TOOL卻應操作是語意漏操作。舊positive scorer的output_format標籤不精確；分析
  依parser分類與expected/actual action區分，不改歷史分數，也不因此觸發semantic retry。
- A→B同時改decision instructions、catalog呈現、Hz說明與輸出示例，不能據此單獨否定
  文字catalog或R3規則。34題含事後選出的8個已知錯例，不是新holdout或全面產品能力排名。

#### 待確認的最小診斷比較（不是新一輪自由調prompt）

尚待區分：D的漏操作主要受decision instructions、catalog呈現，或兩者交互影響。
不從模型承諾開窗就推論其內部思考；先列兩個可區分因素的局部替換，但本次只提議E：

| 對照 | decision instructions | catalog呈現 | 相對D唯一替換 |
| --- | --- | --- | --- |
| D（既有證據） | R3 | 文字 | 無 |
| E（未跑） | 原產品A | 文字 | decision_instructions整塊，含移除R3 reminder |
| F（備案，未排入執行） | R3 | 原產品A的JSON renderer | catalog呈現整塊 |

E/F均維持D的工具schema與Hz說明、無system完整輸出示例、同一RAG/state/user、
model/revision/decoding、parser與一次recovery。不將A的舊Hz內容差異偷偷帶入F。
E直接針對回答/操作決策規則，保持文字catalog不動。先用完整prompt diff確認只替換
指定區塊，再分core20/english6/recovery8跑固定34題（含負向保護），不只重跑三題。
E最多68次生成；現有143加E68加後續74廣度/26off/8native的216次最壞上限為427，
尚留23次餘裕，總450不增加。沒有新增推論。若兩個對照都跑則最壞495，不應先執行
才發現額度不足；因此F不是自動下一輪，需要另行決策，不能犧牲交付gate給它騰額度。
E只說明在D條件下替換規則的局部影響，不是完整factorial、交互作用證明或最佳提示搜尋。
成功與退步逐題列出；若E不成立，回報原因仍未隔離，不追加臨時提示變體。
選定候選後才完成既定廣度/off配對/native/CI與手測；診斷勝出不等於handoff-ready。
Next：與使用者確認上述診斷比較及額度後才實作／開跑，不自動採納回退方案。
