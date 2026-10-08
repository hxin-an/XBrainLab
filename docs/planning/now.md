# XBrainLab Now

最後更新：`2026-10-08`

## Active — R3 產品移植與有界格式恢復

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

### Blocked — 需要基線取捨，不再增加提示變體

唯一有界呈現修理已用完，候選仍比A少3題。不能沿用舊Development例外或調低門檻
直接交手測，也不因額度尚有剩餘繼續試prompt。所有A/B/C/D成功與失敗證據留在
`build/r3-evidence/`，對應source以各report擁有，不改歷史研究結果。
建議使用者決策：退回原產品prompt，保留本輪獨立覆核通過的有界多JSON恢復與直接測試，
重新固定產品候選再完成其相關模型／native／CI驗證。這是產品基線取捨，不宣稱此組合
已測或R3沒有研究價值；R3施工commit與比較證據保留。未獲此決策前不做第二輪提示調整。
已知Assistant偶發匯入卡住根因未證實，Restart只是恢復入口；不宣稱本輪修好。
