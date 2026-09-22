# XBrainLab Now

最後更新：`2026-09-22`

## Active — 無待續施工

後續 DEV 移除 `review_status` 的匯出修正已完成；行為及證據見 [Current](../current.md#assistant-research-baseline)。

2026-09-22 核准的完整 DEV initial 已 scope-complete：1,320 有效量測、獨立判分／capture
核對、報告重建及實際 queue 接續已通過。結果與限制集中於
[Current](../current.md#assistant-research-baseline)，執行契約由
[研究規格](../validation/thesis_protocol.md) 擁有，不在本 plan 重複保存數值。
本輪沒有 PR／push／merge，也不等於產品 native GUI 或正式 TEST 驗收。

後續僅能討論下方未授權的 DEV 調優候選；不自動執行第二套、VALID／TEST，
不重跑已完成的起始基準或歷史 Pilot。以下保留歷史及候選，不作新的施工授權。

## Accepted history — 產品品質線：Import 適配與內部整理

以下保留另一線施工及證據；已由 main@94328196 的 PR #146 合併，不是本線 active 工作。

使用者已授權本輪施工，並要求先更新文件、深入整理完整 Import 路徑，不只修單一 helper。
工作區為 `XBrainLab-product-quality`，分支 `refactor/product-quality`，起點 `8636a754`。
本節是本線唯一施工進度；下方研究里程碑由 Evaluation 線維護，不覆寫或執行其題庫／評測。
PR #143–#145 已進入此 main 基線；舊啟動器、RAG、split receipt 與回應性修理不再 active。
使用者已批准刪除 `wip/data-split-summary`，未合併的 UI 修改未帶入本輪。

### 問題、outcome 與界線

- 正式 BIDS importer 使用 metadata／內容，不以 MOABB 名稱白名單放行；Graz GDF 名稱還原、
  T1／T2 語意防護與轉換端 loader 修補需要分清來源、假設及責任。
- 靜態閱讀發現 preview 與 apply 各自實作 run mapping 查找，對同名檔案唯一性處理不同；
  這是待重現風險，不先宣稱使用者資料已錯誤。
- Outcome：preview／validate／apply／recipe／epoch 的 recording 與 class 解讀一致，
  重複政策收斂；production、直接相關 tests／fixtures／scripts 的去留有具體理由。
- 允許修復已重現的 mapping 誤套或資料一致性缺陷；不改 Graz 自動還原或 Assistant 公開工具。
- 2026-09-21 使用者批准移除僅因內部事件名稱為 T1／T2 而要求逐 recording mapping 的
  特例；現有 Match Labels 選事件、填 class 應足以確認，不新增 UI。外部 labels、既有
  recipe 的明確逐檔 mapping 及一般資料一致性／epoch 前置條件保持。
- 不改研究題庫／runner／scorer／模型／prompt／RAG，不新增下載、不搬資料、不升級共用環境，
  不覆寫任何 worktree 的使用者 settings.json；本輪不是 B0 封存。
- 保留有證據的來源適配，不以特例、LOC 歸零為目標；獨立 UI 打磨留待下一階段討論。

### 施工順序

1. 文件先行：校準已合併歷史；逐段追蹤選取 recordings、events／labels、channels、
   review／apply 與 recipe 的實際 caller，在既有資料架構文件記錄保留／收斂／限制。
2. Baseline：沿用 focused tests，建立真 MNE／Command 路徑的 characterization；
   已重現缺陷先 RED，再修理。查清完整路徑、唯一 basename／run 與 carrier 對應。
3. 收斂：在既有模組重用純函式統一等價查找規則；歧義簡寫不得套用到另一筆 recording。
   保留無歧義輸入與 recipe，維持既有 admission、mutation/publication ownership；
   不新增 authoritative owner、state machine、receipt、通用適配平台或 compatibility 空殼。
4. 相鄰清理：同時檢查專用適配、label 建議、recipe trace、資料一致性與相關腳本；
   確認無 caller 或已有可靠替代證據才刪除 helper／重複測試，不擴張無關 panel。
5. 獨立 review、focused／source-diverse／必要 Windows native 驗證；同候選適用 CI 通過後
   集中一次 Import 局部手測。PR 發布／merge 各依授權，不自行合併。

### 驗證、複雜度與完成

- 正例：完整路徑、唯一檔名／run；不同 run 的相同 T1／T2 不同語意；apply／recipe／epoch 一致。
- 反例：跨 subject/session 同名、重複 run、部分 mapping、對調 carrier、真 stale source；
  失敗不得部分 publication；不更動原始檔案、波形、事件時間。
- 適配：Graz 已知模式保留、名稱／順序／通道數不同不得誤套；BIDS external／embedded／
  no-label 路徑維持。用真物件與 Command evidence 補強 mock-only 覆蓋後才刪重複測試。
- 每個 coherent slice 記錄實際 diff、owner 前後與 production LOC；觸及 root complexity
  門檻先 review。Rollback 為各 slice revert，不用大規模搬檔冒充架構改善。
- 不將舊 134-root campaign 當成本 head 證據；CI 已提供的等價 full checks 不本機重跑。
- Stop：已授權範圍、直接驗證與 review 完成後集中交付；若新政策／UI 決策或必要資源阻擋，
  先完成其餘安全工作並提供具體證據。小 commit、CI pending、context 壓縮不是停止條件。
- 已驗：既有 BIDS／reader baseline 72 passed；新增真 Commands 6 個案例原先 4 failed／2 passed，
  重現 run 簡寫丟失、同名檔案 metadata 誤配、歧義 basename 誤套。修理後另外追到 recipe
  將同名 recordings 的 metadata overrides 壓成單一 basename，初次 apply 正確但重播丟失語意。
- recipe 同名 metadata、完整路徑 mapping remap、部分 remap 誤合併與歧義簡寫被 remap
  誤升格均已有真 Command regression；獨立覆核的 findings 已修理，最後覆核無 blocker。
  原 scope 有歧義的簡寫不因重新命名而取得語意授權；沒有 reviewed mapping 時維持原事件，
  不為測試新增 epoch hint 政策。擴大 focused 曾 255 passed；最後 remap 修理直接相關
  82 passed，需在固定版本重新取得整合 evidence。
- BIDS recommendation 清理為 production +8/-42/net -34 LOC，characterization 先後皆 77 passed；
  Graz reader seam 改用真 MNE 物件補正反例、annotation preservation 比對改為事前 snapshot，
  對應 35 tests 通過。純解析／state owners 不增加；不改推論門檻或 UI。
- T1／T2 修理前的 production 合計 +165/-99/net +66 LOC、5 個既有模組；不新增 owner／module／class。
  Apply 內部 mappings 每批先解析一次，移除 preview/apply 的分歧查找；existing publication
  owner 與 cancellation 不動。相關 catalog／converter 腳本確認仍有用途，本輪未任意刪除。
- Static typing、changed-file lint 與 strict docs portal（42 pages／1,617 links）已通過；
  既有 MNE／NumPy deprecation warnings 保留，不在本輪升級共用環境。
- 候選 6f1cf5f9 已驗 focused 256／source-diverse 4 passed。Windows wizard 19 passed／
  2 failed：原 PR #141 已新增 no-label Back/Next driver，folder trace expectation 卻漏同步；
  基線與候選測試 blob 相同，獨立覆核確認。僅補完整序列中的返回步驟，保留所有 state
  assertions，不改 UI。舊 catalog 因候選需更新而主動中止；保存 partial evidence，不計通過。
- 9a0cc0f0 已完成 focused 256、source-diverse 4、Windows wizard 21 與代表性 catalog
  134 passed；這些是修正 T1／T2 政策前的基線，不代表新修改已驗證。
- T1／T2 repair 已完成：真 Commands 重現填 A/B 後 epoch hint 仍是 T1/T2；真 wizard
  重現完成選擇後仍要求額外確認。名稱特例、專用 helpers、確認與套用分支已移除；
  現在以明確 class maps 決定分類／逐檔差異，不新增 owner／module／UI。
- 替換兩個只保護退役政策的 mock-heavy unit tests，改由真 MNE／Command 與 native UI
  覆蓋：共用 class、明確逐檔優先、recipe replay、事件 sample／class 序列與來源 bytes。
  直接回歸保留同名／歧義／remap 的 epoch 防護；獨立覆核的五項資料流程探測通過，無 blocker。
- 6af61225 已完成 focused 279、source-diverse 4、Windows native 22 與代表性 catalog
  134 passed；詳細結果在 build/import-quality 的同版本 verified artifacts。
  使用者已確認 Windows 原生 T1／T2 → A／B 操作通過；此為局部操作確認，不是全部 Import
  驗收或 merge 授權。2026-09-21 使用者已授權推送／開 PR；仍未授權 merge。

- 2026-09-21 使用者同意的操作路徑覆蓋收尾已完成：既有 UI 測試補單／多檔共用 class、
  返回改名後重新 review、BIDS 內部事件及外部 MAT 的實際 epoch／recipe 語意；CSV／TSV
  原 placeholder 測試升級為真 widget → Commands → epoch／recipe，無 labels 實測 epoch
  拒絕且不改 working data。保留取消／重試／失敗 atomicity 的既有保護；完整對照及限制由
  [validation contract](../validation/README.md#import-support-claims) 擁有，不複製另一份矩陣。
- 收尾僅 tests/docs，production 0 LOC；獨立 review 的多檔 oracle 缺口已修正。首輪外部
  測試抓到等待 worker 而未等待獨立 render timer 的時序錯誤；移除測試內手動刷新，限時
  等待自然繪製後 4/4 通過，原失敗保留。整合 Windows native 30/30、0 skip 通過
  （build/import-quality/path-closure-native-integrated.json），lint 通過。未重跑未變產品的
  134-root catalog，不把既有結果換標成新 head；仍有來源警告與 MNE／NumPy deprecations。
- Next：推送產品品質分支、建立 PR 並追蹤同 head CI，修復 in-scope 失敗；不自行 merge。
  本輪沒有再次改變使用者剛確認的產品行為，不要求重測 T1／T2，也不把局部確認当 merge 同意。
## Completed record — B0 完整執行入口（2026-09-21）

使用者授權的可日常重跑 B0 入口已實作、獨立覆核及實跑全矩陣；
`baseline.cmd` 的固定範圍與用法由[研究規格第 5 節](../validation/thesis_protocol.md)擁有，
實際結果、資源位置與重現限制見 [Current](../current.md#assistant-research-baseline)。

- 重用 frozen runner／scorer／report，沒有新增產品 owner、環境或模型下載；原封存不改。
- 全 300 題與報告驗收、report-only、無重送的 completed resume、中文／空白搬移驗證通過。
  入口測試／相鄰契約與 Windows preflight 完成，測量與各次報告保留。
- 已辨識既有 prompt 的匿名識別／publication counter 變動；不追改 B0，也不把它說成
  完全相同輸入或正式模型排名。正式比較前的非任務資訊控制留待 M4 決策。
- 本輪 scope-complete；沒有產品 UI 變更、push／PR／merge 或 Development／Validation／Test。
  不自動啟動下列 candidate。

## Completed record — 正式 B0 共用修理與封存（2026-09-21）

使用者授權的共用格式／重試修理、相同矩陣重跑及另立正式 B0 已完成。
`assistant-b0-formal-20260921-926d90ea` 固定 `926d90ea`；前期 `ac8af81d` tag、
原始分數與封存不追改。精確版本、結果、封存位置與限制由
[Current](../current.md#assistant-research-baseline) 擁有，契約由 target／研究規格擁有。

- 共用整份 JSON fence 相容與預設一次格式修復，沒有新增 owner／控制層；直接相鄰的
  舊 evaluator observation adapter 及非法 typed-clarification scorer 假陽性亦已修正。
- Focused tests、契約／安全獨立覆核通過；完整 300 題與 320 次 capture、分母、
  逐題判分及報告連結經獨立核對，低分、失敗與先前 partial 原樣保留。
- 新鎖定 Windows 環境真跑單條件 30 題，分數／repair／核對的產品結果一致。
  E 槽封存 6,216 檔逐檔校驗通過，僅移除本輪臨時 checkout／環境；共享資源保留。
- 本輪 scope-complete，不是 native UI 驗收或產品 handoff-ready；未 merge、
  未跑 Validation／Test，也未開始 Development 調優。後續候選須另行確認。

## Future — 完整 DEV 起始基準後的調優（尚未授權）

前期 Pilot／B0 與新版完整 DEV initial 均已完成。
事實與限制見 [Current](../current.md#assistant-research-baseline)，
報告入口／契約見研究規格第 5 節。舊分數與快照不追改。
下一輪若經使用者確認，才依
[研究規格](../validation/thesis_protocol.md) 的每模型最多五套設定規則選擇改善方案；
本輪 initial 已占各模型第一套。只調已允許的提示詞／工具呈現／格式修復，RAG 固定。
不因 Pilot 分數直接調 prompt／RAG、挑模型或啟動
Validation／Test；Test 仍封存且本輪未讀取。

可據本次證據討論的改善最多三項：缺資訊時自行補參數、不得操作時仍選擇工具、
動態 publication 變動下的操作交接。共用 fence 與重複修復已處理；仍存在的模型格式錯誤
不能說成全部解決。這些是候選，不藉報告施工直接改模型或產品。

## Completed record — Assistant Evaluation 準備至 Pilot（2026-09-21）

使用者已確認本輪做到「文件校正 → 非 Test 題庫接入 → 評測系統就緒 → Pilot →
結果報告與改善前基線封存／還原驗證」。不是只做文件，也不自動進入 Development 調優、
正式 Validation／Test 或 B1／B2。研究條件與預算只由
[研究規格](../validation/thesis_protocol.md) 擁有；本節只記執行順序、責任與進度。

### 起始問題、施工範圍與出口

- **起始證據**：既有 calibration 只讀合成觀察；舊 frozen 81-case runner 攔截工具執行，
  不能當成本輪真實 Product Outcome。正常 ChatPanel／Host／Command 與 prompt capture 可重用，
  新題庫讀取與單次決策 scorer 已完成 focused 驗證；五模型配置、真實 outcome 與
  完整 runner／軌跡判分／計時／續跑在本輪開始時尚待施工及驗證。
- **起始題庫狀態**：已接收使用者指定的非 Test Excel，結構為 DEV 264 題／66 families、
  VALID 99 題／33 families，family 無交集。使用者於 2026-09-21 明確確認題目與答案
  全數人工覆核完成；當時實際 runtime fixture 仍須準備，不以人工確認代替執行證據。
  Test 仍由使用者保管，
  不為找題庫而讀取封存題文、答案或其他對話全文。
- **完成出口**：Pilot 全部預定案例有完整可追溯軌跡，測量與判分可核對，交付分條件結果、
  有效失敗／無效測量、延遲與資源成本、後續實驗可行性，以及可還原的改善前基線。
  模型低分不是未完成；缺少條件／紀錄或只跑工程 smoke 不能算 Pilot 完成。
- **假設**：使用英文單回合題庫及既有產品工具契約。必要的取消、停止、狀態過期與晚到結果
  只作工程保護，不擴張為未批准的正式多輪實驗。
- **範圍**：題庫格式／oracle 接合、真實觀測、scorer、模型研究接入、單一實驗入口、
  計時／軌跡／結果彙整、安全續跑、Pilot 與封存。直接必要缺陷先重現、最小修理。
- **非目標**：不改公開工具、產品模型清單、UI layout／文字／流程；不調 prompt／RAG 追分，
  不做全面重構、EEG 模型研究或重新下載整套 EEG 資料。Test 不讀、不跑。
- **UI 確認**：本輪不含可見 UI 變更；真實操作觀測沿用現有 UI。若修理需要改可見互動
  或 public contract，先提出具體決策，不把本輪批准當作通用授權。

### 雙線工作區與共用邊界

| 工作線 | 工作目錄／起始 branch | 責任 |
| --- | --- | --- |
| Evaluation（本線） | `D:\workspace_v2\projects\lab\XBrainLab-evaluation`；`feat/assistant-evaluation` | 本節授權範圍、研究規格、評測與基線 |
| 產品品質（另一對話） | `D:\workspace_v2\projects\lab\XBrainLab-product-quality`；`refactor/product-quality` | 另行確認的清理、重構與 UI 調整；不是本線的隱含施工範圍 |

兩個 worktree 從 `main@8636a754` 建立，Git 決定最新 branch／dirty 事實；`main` 仍為唯一
產品基線。工作目錄可持續使用，task branch 仍須保持明確目標，不演變為永久平行產品。

- 本線擁有研究規格與 Evaluation active 內容；另一線更新自己的計畫區塊，不覆寫本線進度。
  本文件仍是唯一 active plan，不另造第二套總計畫。合併時保留兩線各自有效更新。
- Command API、工具／完成語意、狀態 publication、資料解讀與 UI 觀測接點是共享邊界；
  修改前協調 owner 與受影響案例，不各自建立相同責任，也不自行合入另一線未完成修改。
- 每輪實驗固定 source／設定／模型／題庫／scorer 身分；只在輪次之間明確同步已接受的
  `main`。中途不 pull／換 source，改版另立 run 身分，不混用前後結果。
- 不複製大型模型與 EEG corpus；必要來源按不可變 revision／hash 管理。各 worktree 的
  可寫設定、run output、log、暫存與 RAG index 須分離或有明確唯讀共用邊界，先驗證再執行。
  主工作區 `settings.json` 不覆寫、不 stage。
- 優先使用既有 Windows 環境；實驗期間不得升級共用依賴。若需要不同依賴，先確認有界的
  隔離環境與空間方案，不默默改另一線。量延遲期間不並行 GPU 訓練、模型推論或重型測試。
- 正式實驗與 B0 不靠 worktree 留存保證：封存內容／還原要求由研究規格擁有。

### 實作與驗證順序

1. **文件與接收**：移除已結束 dispatch、保存本輪與雙線決策；核對非 Test 題庫路徑與
   元資料。只有當題使用者輸入可進入該回合；oracle／答案與其他題庫內容不得進入 prompt、
   few-shot 或 RAG。Validation 不用來除錯。只取得使用者提供的
   Test 封存狀態／數量／身分，不代稱已獨立審題。
2. **題庫與 scorer**：沿用既有 parser／schema，實作正式研究的三類／分層判分與完整性檢查；
   用已知正反例保護工具／參數錯誤、正常不執行、Host 擋錯不算模型答對、缺失軌跡與錯誤身分。
   不覆寫舊 calibration 或 frozen 81-case 的規則與歷史成績。
3. **真實觀測與 runner**：正常 ChatPanel／Host／Command 路徑接 case／attempt／terminal，
   開窗就緒與完整操作 outcome 分開；產品 owner 決定 readiness、confirmation、mutation。
   補選一／多個／全部條件、輸入輸出與各時間段、失敗彙整與安全續跑，不新建產品 owner。
4. **模型與資源**：唯讀核對五模型精確來源、revision、權重大小、VRAM、授權與 cache。
   缺模型／條款需取得對應授權，不 silent fallback、不自動增加 cache 上限。固定配置後，
   有界載入、暖機與非 Test smoke；RAG on 須真正可用，degraded 不能當作 on 成績。
5. **Pilot**：題庫／系統 gate 通過後，按研究規格固定 manifest、題號、配置與輸出；
   先小階段驗證測量，再補完整矩陣。有效低分照跑照留；測量故障修理後只補受影響部分，
   不以看見答案後重試挑分數。機器時間到預算上限即保存 partial，不自行延長。
6. **收尾與封存**：核對逐題軌跡／分母／失敗與量測界線，交付粗略成本與限制；
   保存 source、環境、模型／資料身分、重跑命令與原始結果，實際還原驗證 B0，
   不開始 B1／B2，不將 Pilot 當正式獨立 Test 或穩定 P95／模型排名。

每個直接必要 slice 實作前在本節補 call sites、具體 focused validation 與回退邊界；
新行為先 RED→GREEN，refactor 使用 passing baseline。每次修改 review，高風險資料／
async／評測證據採獨立覆核；同一份實際 diff 與測量證據由主 agent 驗收。
不為每個內部 slice 要求使用者重測 GUI；產品行為變更仍遵守正式 handoff／merge 規則。
Pilot 完成不等於產品手測／merge 同意；外部寫入與交付仍依 repo 授權邊界。

**完成位置**：題庫／scorer、研究 runtime 注入、五模型檔案取得、全部 selected fixture、
真 Qt observation 與完整 runner 已完成 focused 驗證；Gemma 經批准 NF4 配置通過 GPU
工程檢查。第一版 frozen Pilot `8a7935c3` 在 176/300 fail closed：Phi-4 對
`DEV-C06-01-V3` 錯誤呼叫 `switch_panel(visualization, 3d_plot)`，產品正常顯示既有
`VRAM Warning`，但 driver 把該可歸因的產品警告誤記為 `unexpected_dialog`／無效量測。
已完成的低分與失敗原樣保留，不作挑分重送；此 run 僅是量測框架缺口證據，不納入正式
Pilot 比較。完整 300 題 Pilot 與 B0 封存／還原結果見本節後續完成紀錄及
[Current](../current.md)；下列施工細節保留為歷史證據，不再是 active dispatch。
題庫 intake 證據與來源如下。
來源為使用者指定的 `C:\Users\Administrator\Downloads\題型_已審不含TEST.xlsx`，
SHA-256 `2161af9932950e2a0726daeae3d744935d8d1bc6f408d739b2240d2752a29c23`。
只讀原檔；工作表、split、ID／family／fixture 與 ground-truth 對應 fail closed，
不發現其他檔案或讀取 Test。原 workbook 的 363 筆 review_status 均仍為待人工複核，
runtime 證據 source 為 `8314b590`。使用者於 2026-09-21 已確認全部人工覆核完成；
此為原 workbook hash 所對應的補充宣告，不覆寫原檔／舊 runtime 證據。

直接施工接點：`scripts/dev/assistant_pilot_bank.py` 讀取這份明確 XLSX 契約並輸出有
source identity 的非 Test bank；`scripts/dev/assistant_pilot_scoring.py` 以既有
`CommandParser.parse_product`、`ToolSchemaValidator`／工具 registry 做離線決策判分。
保留 workbook oracle／fixture 原始欄位與舊證據標記；供模型的輸入與 oracle 分離。
Scorer 區分 Action、Clarification、No-call，正常 respond_to_user 不要求 exact message
或 typed pending receipt；錯誤 call 被 Host 擋住仍不能變成模型正確。這只是決策判分，
不宣稱 backend／GUI 成功，不改舊 calibration 或 frozen 81-case。
刪除候選：無；既有 product owner 前後不變，production LOC +0/-0，僅 scripts／tests，
不增加 state machine、receipt 或相容分支。XLSX 不新增套件／修改共用環境。
Focused：新增相應 unit tests 先 RED→GREEN；覆蓋正常讀取、split／family 洩漏、重複／
缺漏／衝突 ID、無效 JSON、受限壓縮／XML、source 身分，以及正／錯工具參數、
布林不等於數值、正常／空白／invalid 不操作回覆、初次／修復後分開與不偷用 oracle。
真 workbook 做 metadata／完整性核對，題庫內容不 commit。獨立 review 後才接實際 runtime；
rollback 僅移除本 slice 新 scripts／tests 與對應計畫，不改原 XLSX／模型／產品。
**已查**：bank／selection／models／fixture／scorer 與既有 calibration 的 Windows
focused tests 合計 226 通過；runtime 注入及相鄰 default／spawn／cancel tests 132 通過；
MainWindow factory／既有 UI shutdown tests 28 通過。scorer、runtime 與 fixture 經獨立 review，
主 agent 已查實際 diff／測試及真 workbook；Ruff、diff check 通過。第三方 deprecation
warnings 保留，未改環境。真 workbook 363 題 oracle schema 全數合法，人工覆核由使用者確認。
正常 controller 的 generation request／events、activity、Command completion 與 turn terminal
可作觀測接點；舊 runner 明確 suppress 工具執行，不沿用其結果作真實 outcome。
既有 TurnMetrics 包含整個 turn，UI request success 也不代表畫面已就緒，須分別觀測。
既有 Windows 環境為 Python 3.12.10／torch 2.11.0+cu130／transformers 4.57.6；
未安裝或升級。三個批准 snapshot 的既有 HF 帳號 access 通過；39 個必要檔案下載及
大小／官方 LFS SHA-256 核對完成，新增 22,768,349,036 bytes，盤點總 cache
41,711,365,409 bytes（含既有 repo/cache 與保守 WSL 用量），未刪既有資料。
**已完成的量測修理**：上述 UI 實例已補 RED→GREEN characterization；只將可識別、由本回合 action 引起的
產品資訊警告記為 product outcome 並安全關閉，未知 dialog 仍 fail closed。Windows runner
子程序已加 `CREATE_NO_WINDOW`，保留 stdout/stderr、精確 PID、timeout、terminate/kill 與
cleanup 語意；相鄰 117 tests 與 focused Ruff 通過，diff review 無 blocker。

第二版 frozen run `efa46489` 在 35 個完整結果後依使用者要求停止；精確執行中 child 已確認
退出，partial 只保留工程證據、不納入 Pilot。這 36 份已寫 result 的 baseline 顯示模型載入
中位數 7.424 s、整題中位數 12.854 s，載入占總 wall time 57.0%；fixture 中位數 0.289 s、
decision 中位數 2.049 s。每題 fresh process 雖隔離嚴格，但 300 次載入不是研究條件，模型
載入本來也另行統計，故改成每個 model×RAG condition 一個 owned child／一次 cold load，
同條件 30 題依序執行。

Condition worker 只重構 `scripts/dev` runner/case seam，不改產品 runtime owner、prompt、題庫、
scorer、UI 或 public contract。每題沿用既有正式 `reset_session` 與 `reset_conversation`，重新
建立 fixture、trace、UI driver、case deadline 與 result；進題前 fail closed 核對零 active
operation／turn／pending interaction、空 conversation/transcript、初始 pipeline stage 與同一
pinned runtime。prompt capture 需用序號範圍精確綁定每題，warmup 每 condition 只做一次。
Parent 對 condition child 保留精確 PID、硬 timeout、stdout/stderr、journal 與不重送 started
condition；任一 case 或 reset audit 失敗立即停止並保留所有已完成結果。先用 synthetic/real Qt
characterization 證明兩題不同 fixture／conversation 無污染、child timeout cleanup 與 resume
語意，再跑一個 2-case 真 GPU before/after probe，確認只載入一次且決策／capture 完整，最後
以新 clean commit 從 0/300 重跑。不得把舊 176／35 題與新 source 混成一批。

Owner 前後不變：產品 model process 仍由既有 LocalRuntimeProcessOwner 擁有，Study mutation
仍由 ApplicationService 擁有；研究 parent 由 per-case child scheduling 收斂成 per-condition
child scheduling，不新增產品 owner/state machine/receipt。刪除候選為每題重複 runtime
bootstrap、warmup 與 RAG warmup。回退為 condition runner/case adapter 與 tests；若無法證明
reset isolation，回到 fresh-process 設計而不宣稱效能改善。production LOC +0/-0。

**Condition batching 施工狀態**：parent manifest 已升為 v2，依 condition 分成 10 個 hidden
Windows children；每個 child 一次 cold load／warmup，30 題各有獨立 hard watchdog、fixture、
trace、UI driver evidence、prompt capture range 與 result。case 之間經正式 reset owners 並
檢查空 pipeline／conversation／transcript／pending interaction／owned jobs；parent 只為 child
實際回報的 case 建 journal terminal，不把未開始題偽造成失敗。Report 將 model load／warmup
每 condition 計一次，case timing 仍逐題。相關 128 tests 與 Ruff 已通過。
第一個真 Phi-4/RAG-off probe 在模型完成一次載入／warmup後、首題進入 boundary audit 時
fail closed：產品 `pipeline_stage` 契約為字串，runner 誤當 Enum 取 `.value`。沒有送題或產生
模型成績，condition cleanup 通過。已補最小 RED→GREEN 與 parent 相鄰 29 tests；舊 probe
只保留工程失敗證據。修正後以 frozen `c31a8559` 重跑同一真 GPU／真 Qt condition：30/30
結果均為 recorded、cleanup 與 case boundary 通過，conversation／visible transcript／active
operation／pending interaction 皆在每題前歸零，逐題 prompt capture 與 input audit 無 issue。
模型只 cold load 一次（8.002 s），30 題 condition wall time 108.011 s；相對先前 fresh-process
36 題實測的整題中位數 12.854 s，30 題推估 385.620 s，減少約 72.0% 無研究價值的等待。
Probe report 保留為 partial engineering evidence：有效 decision 30/30、無 missing／invalid／
timeout，first／final macro 皆 0.648；低分不重送也不當成 runner 失敗。此 probe 當時仍不是
Pilot 完成；後續完整 frozen 300 題結果如下。
當時已有基本報表與 B0 封存／環境還原；後續已補完整可讀報告及還原後真實測量，見 Current。
UI layout／文案／產品互動不變；只改研究 driver 對既有警告的觀測分類與 runner 的 console
presentation。回退為這兩個 script seam 與 tests，不改產品 owner/public contract。
**當時出口**：frozen `ac8af81d` 的 300/300 題完整執行、基本報告與 B0 環境還原已完成；
Test 未讀取。缺資訊題的 prompt/history/RAG 由逐題 input audit 核對，fixture setup 不取代此 gate。

模型唯讀 preflight 找到下列官方 pin，使用者於 2026-09-21 批准下載；尚未認證載入成功：

| 官方來源 | 候選 revision | Safetensors 權重大小 | 權限 |
| --- | --- | ---: | --- |
| [Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct) | `cfbefacb99257ffa30c83adab238a50856ac3083` | 7.672 GB | MIT；已下載／核對 |
| [Llama-3.2-3B-Instruct](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct) | `0cb88a4f764b7a12671c53f0838cd831a0843b95` | 6.426 GB | 既有帳號 access 通過；已下載／核對 |
| [gemma-3-4b-it](https://huggingface.co/google/gemma-3-4b-it) | `093f9f388b31de276ce2de164bdc2081324b9767` | 8.600 GB | 既有帳號 access 通過；已下載／核對 |

官方 shard metadata 加上既有兩個 Granite，五模型權重合計約 34.571 GB，尚不含其他
cache／設定／tokenizer；超過原 20 GB 總上限。使用者已批准上述精確
來源下載至 `D:\XBrainLabCache\models`、研究期間總模型 cache 上限提高至 50 GB；先
精確盤點現有用量，若仍超限便停，不刪共用模型、不繞過條款，也不代使用者接受條款。
五個 pinned tokenizer 都完成原生 system／untrusted context／request template 檢查。
兩個 Granite、Phi、Llama 依序完成 Windows GPU BF16 load→32-token engineering generate→
close，四個 owned child 均確認退出。32-token smoke 不等於正式 512-token／8K prompt
壓力測試、GUI tool outcome 或 Pilot 分數。Gemma 的 tokenizer 成功，但 load 在物化前拒絕。
全部維持 `trust_remote_code=False`、local-files-only，不代接受條款、升級或 silent fallback。
產品 allow-list 仍只含兩個 Granite；研究已重用既有 `engine_factory`／lifecycle 接點。

**Gemma 限制**：研究候選估算 12,000,000,000 bytes 尚非實測 peak；既有 model-load guard
在 required > 75% available 時 fail closed，因此需至少 16,000,000,000 bytes 可用。
所有本 agent 模型程序退出後再查為 15,738,077,184 bytes，尚差 261,922,816 bytes。
這是 admission rejection，不是 OOM、模型錯誤或準確率；不為過 gate 降低未測估算、不
關無關程序。原生權重 header 確認 BF16 tensor 共 8,600,158,944 bytes；加最保守 full-length
KV 為 9.741 GB，但尚未含 activation/workspace/allocator，不能用來假裝總 peak 已知。
使用者後續批准 Gemma NF4/BF16，量化 estimate 已依實測上調為 11 GB，沒有繞過 guard。
本機 evidence：ignored `build/dev-artifacts/model-preparation-20260921/`，含下載 receipt、
各模型 smoke（包括 Gemma 失敗）、bank-hash selection 與 initial fixture report。

### 直接必要 runtime slice（2026-09-21）

**2026-09-21 已批准 Gemma 量化修理**：只將 Gemma 研究配置改為 bitsandbytes
NF4 4-bit／BF16 compute，其他四模型不變。沿用官方 pin／已下載權重，不改日常
settings、不下載或升級共用環境。原 12 GB BF16 估算被既有 75% guard 拒絕不是 OOM。
先 RED tests，再由既有 immutable spec 攜帶量化 estimate/type/compute；research factory
固定配置並拒絕漂移；default product 4-bit 行為不變。研究量化固定指定 GPU，不 offload。
初始 estimate 依 pinned tensor headers：BF16 8.600 GB，其中 embedding 等未量化
1.355 GB、候選 Linear 7.245 GB；保留 metadata、保守 8K KV、activation/workspace
與載入暫存餘裕，先估 8 GB（未實測）。保留既有 75%/90% guard 與 OOM cleanup。
Focused：量化/非量化 admission、無 estimate/漂移拒絕、dtype/device/pin、相鄰載入與
OOM tests；Windows native load、代表性 prompt/output、peak memory、cancel/reload/close。
新 evidence 不覆寫舊拒絕；實測超出估算須上調重驗，不為過 gate 降低。
Owners 不變，無新 class/state/receipt；optional spec fields 與既有 backend branch。
UI unchanged；回退只移除此配置接合，不刪共用模型或證據。出口為安全實測及獨立 review
後接續 runner/Pilot，不將 smoke 當 Pilot 或 BF16 accuracy。

**量化驗證結果**：初始 7,025-token input 的 peak reserved 8.869 GB 超過 8 GB
analytic estimate；如實保存並上調為 11 GB。較強 7,671 input＋512 output 原生生成
35.62 秒，peak allocated 9.375 GB／reserved 9.878 GB、400 個 Linear4bit，全部 CUDA。
直接 engine 同程序 unload 後仍保留 allocator pool，故 reload 被 11 GB guard 拒絕；
保留此限制，不把它說成成功。產品實際 owned-process 邊界另驗兩輪載入／串流／
並行消費時取消／再生成／close；均成功且 child 退出，可用顯存前後同為
15,738,077,184 bytes。第一版 cancellation probe 同執行緒不消費 stream，觸發正常
hard-stop/restart-required；修正 probe 為產品同樣的並行消費，舊失敗保留。
Windows focused quantization／catalog／backend／injection 合計 99 tests 通過；
獨立 source review 無 blocker。工程 artifacts 為 model-preparation-20260921 下
gemma-nf4-*／gemma-owned-nf4-*，不計入 Pilot 分母，未宣稱 BF16 速度或品質等價。

證據：`AgentWorker` 已使用 owned process，但固定建構預設 engine，且每次生成重新讀取
日常 settings；`LocalBackend` 三處直接取 product spec；系統角色與連續 user roles 能力
混在同一 flag。五模型研究不可經 Settings 正規化而無聲換回 Granite。
Outcome：既有 runtime 注入不可變研究 spec／frozen generation config；預設產品行為與
allow-list 不變。UI 文案／layout／public tools 不變，不建立第二個 controller 或取消 owner。
步驟／接點：`LocalBackend` explicit spec 與固定 template kwargs；既有 `LLMEngine`
接受 backend factory；`AgentWorker` 透過既有 `LocalRuntimeProcessOwner.engine_factory`
傳入可 pickle 的研究 factory，選用 frozen config loader；`LLMController` 選用 worker factory。
`LocalModelSpec` 分開連續 user role 能力，Granite 現有 prompt 保持不變；Gemma 只作官方
template 必要相容，Llama 固定模板日期。不改 product catalog membership、download policy
或 runtime lease／cancel／close 實作；MainWindow 接合另先核對既有 lifecycle seam。
Complexity review：刪除／收斂候選為重複 spec lookup；owners 前後不變，不新增 public class、
state machine 或 receipt。實際 runtime production +91/-12/net +79 LOC／5 files，屬研究
接入功能而非純重構；MainWindow 接點另 +5/-2/net +3。可獨立回退，不刪下載模型／題庫。
Focused：既有 local backend／engine／worker／controller characterization 先通過；新增
default policy 拒絕、spec/config mismatch、固定模板與 settings、Windows spawn／stream／
cancel／close 測試。外部權重隔離允許 mock，但 owned process lifecycle 必須實際執行。
獨立覆核 default-policy bypass、父子程序身分漂移與 shutdown；主 agent 核對實際 diff。
此 slice 出口為上述工程證據閉合，之後接真實 GUI／Command 觀測；不冒充 Pilot 完成。
研究端接點 `scripts/dev/assistant_pilot_models.py` 僅固定五個既有／批准 spec，重用
LaunchSpec／SettingsSnapshot 與 module-level engine factory；拒絕未列模型，不替產品
新增 resolver policy。Pilot 初始工程配置沿用 structured-decision greedy／512 output，
8,192 context、seed 0；四模型 BF16，Gemma 依後續批准 NF4/BF16；
Llama template 日期固定 2026-09-21。
這是先行 smoke／Pilot 配置，不提升為正式實驗參數。Focused：完整 pins、未知模型拒絕、
frozen config 重建互不污染、spawn pickle 身分、existing two-model product catalog 不變。

Pilot selection 準備：不依模型結果選題。DEV A01–A18／C01–C06 各選字典序第一個
family，N01–N03 各選前兩個 family；family 內選最長 input，平手以 case ID 排序。
保留 30 個不同 family、18／6／6 配額、18 action tools；第一階段固定 A05、A08、
C01、C02、N02 第一個 family、N03 第一個 family（2／2／2、含 GUI 與直接操作）。
只保存 bank hash、選題規則、ID 與分階段順序，oracle 不進 prompt；拒絕錯誤 ID、
不足配額／重複 action tool／VALID 入選。接點為既有 `assistant_pilot_bank.py` 的純函式，
focused synthetic bank tests 保護順序不受輸入排列影響、更新 bank hash 不能偷用舊身分。
實際選題最長版本僅 37–81 字元：包含本題庫相對較長變體，不宣稱 long-context 壓測。

### 真實 fixture／UI 接合 slice

**正常路徑 observation slice**：重用 controller generation／dispatcher／runtime signals，
script 收集 per-case/per-generation 原始 input/output、confirmation、Command、UI handoff
與 turn terminal；不接受 oracle、不代執行或推導成功。controller 只在既有 parser／
ToolAttemptDecision 位置加 best-effort 診斷（含拒絕）；不重評 admission，不新增 owner。
觀測有界、時間戳與關聯身分明確，缺漏／截斷標為無效量測；GUI visible-ready 由後續
實際 Qt driver 另觀測。先已知完整／拒絕／錯誤／缺失 trace tests，再真 Qt controller
路徑驗證；獨立 lifecycle review。無可見 UI／工具契約變更；回退只移除此診斷接點與
research collector，不改既有執行／取消政策。此 slice 完成後仍須 runner 與真 Pilot。
RAG off 由 controller 的明確研究建構選項跳過 start/retrieve，沿用既有無檢索組裝路徑；
預設 on 不變，不用 failed/degraded retriever 假裝 off。On 須另驗 ready/檢索無錯誤，
embedding 唯讀共用、可寫 vectors 在研究 run 隔離；corpus 不加題目／答案。

**真 Qt driver／單一入口**：script 只對 isolated synthetic case 的實際 confirmation card
按批准；按真 handoff route 觀測 visible/enabled dialog 或實際 panel/view，保存畫面，
開窗題在 ready 後透過真 Cancel 收尾。不憑 oracle 挑畫面、不合成 resolution，不對未知
提示框任意 Yes。Start/Saliency 另待真 job terminal，不能以 turn terminal 代替。
每題 fresh Study/MainWindow/owned runtime，先固定 settings/prompt/log/RAG/output 隔離；
模型 load/warmup 與單次決策120秒分列，case process 有硬 timeout；只停自己的程序。
父入口固定 DEV30／5model／RAGon-off／seed0，先6題60次再24題240次，支援指定條件與
同身分續跑，不覆寫結果或重送已開始但未終結的case。總4小時含setup/load/cleanup；
到限保存partial。Source/environment/hash漂移拒絕續跑；先合成正反例與真Qt工程驗證，
再凍結commit跑Pilot。A14 CPU live fixture 明確10000epoch ceiling，仍只有12trials；
只為維持running初態，在decision完成/120秒時立即stop，另≤10秒cleanup；自然先完成
為fixture drift不是模型錯誤。其他completed fixtures仍1epoch，不增加EEG研究範圍。

問題：舊 fixture 是 128 Hz／4 channels，與本題庫的 250／256／512 Hz／5 channels 不符；
部分舊 helper 會刪共用 temp 目錄，不能直接沿用。`MainWindow.init_agent` 固定 manager
建構，研究不能在啟動後偷換 controller／engine 或以 debug transport 取代正常路徑。
Outcome：逐 case 專屬新目錄中的 deterministic EEG，經既有 Scan→Preview→Validate→Apply
與 preprocess／epoch／split／train Commands 產生真實狀態；fixture、publication、callable
tool 必須核對，不以人工 stage 字串或 oracle 偽造。fixture 配置只建初始狀態，不執行待測動作。
接點：研究 script `assistant_pilot_fixture.py` 與直接 integration tests；先覆蓋 empty、
data_loaded、preprocessed、epoch_ready、dataset_ready，完成／執行中 training 與 saliency
必須用真 job，另驗取消／close。不得呼叫會刪 global temp 的舊 helper，原資料唯讀。
UI 只為 `MainWindow` 加可選 manager factory，預設仍建相同 AgentManager；研究沿用既有
AgentManager(runtime_lifecycle=...) 與 lifecycle.start(launch_spec=...)，在 UI 綁定後啟動。
不新增研究 resolver、不走 Settings／model switch，不改可見 UI；controller／Command
owner 不變。constructor/init_agent 實際 +5/-2/net +3 LOC，無新 owner。
Focused：預設 MainWindow lifecycle／shutdown baseline、factory 真 Qt 綁定與 close；fixture
以實際 service publication／channel／sfreq／event／split 檢查。相鄰 UI 流程不全套重測。
Rollback 僅移除 factory 參數與新研究 script/tests；不清共用 cache、原始題庫或 EEG 檔案。
slice 出口後接 observer／runner，非 Pilot 完成；等待 signal／GUI handoff／模型錯誤各自記錄。
實際 30 個選定 DEV 的 initial-state fixtures 均已經真 Commands 驗證；另補五個
job-dependent case 的真 CPU training／Gradient saliency，fixture suite 32 tests 通過。
真 Qt driver 及 adjacent host 17 tests 通過，包含真 completed saliency render。
以上只是初態及量測準備，不是 30 題模型結果或完整 Pilot。
observer source review：既有 generation request/events、dispatcher input/confirmation、
command completion 與 runtime turn terminal 可重用；Host admission 及可見 surface-ready
尚無完整觀測。須在既有判定接點加 failure-isolated diagnostic notification，或研究端
Qt show/next-loop 觀察，不攔截 execute、重算 admission 或把 modal 關閉當開窗延遲。

**2026-09-21 runner 整合修理／證據**：原 helper 在 composer 空白時等 disabled Send，
真 host 工程 attempt2 因而未送出；已改填入後等待 ready，真 Qt regression 保護。
Gemma attempt3 正常走完三次格式錯誤與耗盡終態，完整 raw／capture／scorer、cleanup；
這是有效模型失敗，不是正確回答。Granite4 RAG-on engineering bandpass 已真正執行
8–30 Hz 濾波、記錄 Command／publication 並正常 close。兩者不是 workbook 或 Pilot。
Decision clock 改採實際交付／回覆事件，不以 provisional envelope 結束修復計時；
job 從永久 identity/result 追蹤，不只 poll active；UI pending drain 後才產出結果。
Windows venv launcher 有兩層 PID：已用 base interpreter＋child-local launcher hint，
原生確認實際 PID＝Popen PID 且仍用同 venv；不終止無關程序。
Training 初態改在暖機後建立；turn 終態或120秒定點停止 runner 自有初始 CPU job，
明列 runner cleanup，不算模型 stop 成功。真正 stop engineering case 被 Host stale
publication 擋住，保留原始證據並釐清，不修改模型/prompt來追分。
Prompt provenance 核對初次 fresh history、當題 input、state card 與 untrusted RAG 分離；
缺資訊英文語意仍由人工覆核，不宣稱字串檢查能證明。後續已完成 Product Outcome、
報表、callback exception／cancel工程檢查及 source freeze，再完成全部 300 題；未因 checkpoint 停止。
整合 complexity review：production 六個既有 files 共 +197/-24/net+173 LOC，
owner 數不變；沒有新增 production class/module/state machine/receipt。研究 scripts
分別擁有 bank、fixture、配置、passive trace、UI driver、case composition、sequential
journal 與離線報表，均不替代 ApplicationService／Host policy。暫無可刪的產品 owner；
需要的注入 seam 可整組回退，原模型／設定／題庫不動。逐題 fresh runtime 的載入成本
獨立報告；這輪先確保可核對，並不宣稱此 runner 已優化成最高吞吐量。
取消的 prompt capture 另保護 late-chunk 邊界：僅 host terminal 與 capture status
均 cancelled 時，可接受 host raw 是 child raw 的嚴格 prefix，保留未觀測尾段長度與
兩份原文；scorer 不使用該尾段補分。完成／錯誤或非 prefix 不一致仍無效。
真正提交後、生成前便達決策 deadline，須有同題 submission＋cancelled terminal；
可記為尚未送入模型的有效 timeout，不偽造 prompt。Qt poll exception 留存 error 後
走正常清理；不能穿出 callback 造成無證據的 native abort。
兩批整合 focused tests 為146＋137通過；之後直接新增的報表／callback／取消 tests
另依其實際結果核對。兩個 MkDocs strict build通過。實際 Windows --prepare 已核對
300 jobs／五模型／embedding hash；執行拒絕 dirty source，後續完整 Pilot 已由 clean frozen source 完成。
最後的 Product Outcome 已接合：正確 decision／Host blocked／實際 Command／GUI
handoff 分列；driver Cancel 只證明可開窗，不說匯入完成。錯誤工具真的執行仍保留
observed_actions；Saliency 精確綁定本次 compute operation ID，不以舊 fixture job代替。
有匹配 request、clock、screenshot 的 UI timeout／render failure 是有效產品失敗，
缺觀測才是無效量測。新 saliency engineering attempt2 已真模型執行／渲染完成並
通過新 binding；舊 artifact 不補造 ID 或覆寫。獨立覆核 blocker 已解除。
Runtime／passive observer 切片提交於 `aba24e5c`；最終 runner 由 clean `ac8af81d` 執行完整
manifest。300/300 均 recorded，10 個 condition cleanup、每題 boundary／capture／input audit
全數通過；正式 report 為 non-partial、完整 selected schedule，總 active time 1,876.047 秒。
模型錯誤與低分照留不重送。B0 tag 為 `assistant-b0-20260921-ac8af81d`；E 槽封存約 1.4 GB、
3,136 個檔案逐檔 SHA-256 通過。五模型 66 個 snapshot 檔（34,655,741,445 bytes）與 11 個
embedding 檔（91,578,415 bytes）重算一致；大型資源維持 D 槽單一受控 cache，不重複複製。
從 bundle 在 E 槽隔離 checkout、由外部 Poetry 2.3.4 建立全新 Windows venv，三個 PyTorch
套件均為 `+cu130`、`pip check` 通過，非 Test prepare 重建 300 jobs 且所有身份相符。
第一次把 Poetry 裝入目標 venv 的錯誤方法與 PowerShell 中文路徑失敗均保留；修正後 ASCII
wrapper 的 PrepareOnly 單一命令通過。這不是產品 merge 批准或正式模型排名。

**歷史交付更正**：上述完成宣稱未區分基本報表與完整可讀輸出，也未取得還原後真模型／工具
測量；後續補驗及限制由 Current 擁有。M4 仍是後續研究決策。Context compaction、完成一個
slice、CI pending 不是完成。

## 已結束的共同基線

PR #143 啟動器、#144 研究準備與 #145 RAG／直接手測修理已合併；
本輪起始 main 為 `8636a754`，實際 Git／PR 擁有版本事實，不重做舊候選／手測。
#145 包含 Assistant preprocess 回應性、首次 data split receipt stale 與 Visualization
publication 修理。舊 81-case 證據仍有原先 bounded 限制，不是本研究 Pilot 成績。
Split WIP 已依使用者批准刪除，不能再列為待保留分支；主工作區本機設定、資料、
必要歷史證據與共用環境保留。

## 歷史 — 前期第二主線研究里程碑（M1 核對、M2 與 M3）

2026-09-19 使用者確認先備妥完整計畫與里程碑，完成題庫及系統前置驗證，再進入 pilot。
本節保存前期 Pilot 的歷史安排，不再派工；新版初始基準的結果見 Current，
後續候選以上方 Future 為準。[Assistant 研究與實驗規格](../validation/thesis_protocol.md)
擁有目前題數、模型、計分、實驗條件、預算與證據契約。

- **起始問題與證據**：已累積方法決策，但逐項討論缺乏整體交付順序；研究規格第 7 節當時明列
  正式題庫、五模型 runner 與完整 outcome／報告接合未完成。舊 calibration 不是新實驗就緒證據。
- **Outcome**：以 M0–M6 串起計畫、題庫、系統、pilot、改善、選版與結果；每階段有可核對出口，
  不用「系統應該沒問題」或完成一個小切片代替整階段完成。
- **目前位置**：M1／M2 與 M3 Pilot 已完成；非 Test 題庫、fixture、五模型 runner、真實 outcome、
  report 與 B0 還原均有 exact-source 證據。Test 仍由使用者封存，本輪未讀取。
- **下一步**：M4 Development 仍是 candidate；先由使用者確認有限改善範圍與速度目標，再施工。
  未定的正式 Validation／Test 細節仍於原決策時點處理，不提前解封或以 Pilot 選正式冠軍。
- **已完成 scope／non-goals**：以上方已授權範圍及明確三模型下載批准為準；不包括代接受新模型條款、
  任意產品契約／可見 UI 改動、正式 Validation／Test 或 M4–M6。封存 Test 不讀。
- **本次完成條件**：Pilot 報告與改善前基線封存／還原驗證；不是只交付文件，
  也不因此宣稱 M4–M6 完成或產品 handoff-ready。

### 完整里程碑與依賴

依賴順序：**M0 → M1 與 M2 平行準備 → 兩者皆通過 → M3 → M4 → M5 → M6**。
平行指工作安排；獨立且有益的 agent 分工依 repo 規則，GPU 排程與背景長跑仍受本輪預算／隔離限制。

| 里程碑 | 交付物 | 驗收與下一階段入口 | 主要分工 |
| --- | --- | --- | --- |
| M0 研究／施工計畫定稿 | 研究問題、已確認規則、題目模板、準備工作範圍、資源方案及待定項時點 | M1／M2 不存在會阻擋施工的契約／授權缺口；後續決策有 owner 和截止階段，不要求先猜實測值 | Agent 整理整包建議；使用者核對研究意圖與授權 |
| M1 題庫準備 | 規格第 3 節的完整題庫、oracle、初始狀態、family／split 清單及封存資料 | 題數與分組符合規格、可判分、語意經審查；Test 由使用者封存，開發端沒有讀取權 | 使用者負責人工內容與 Test；agent 協助非 Test 模板、改寫、檢查 |
| M2 系統與評測工具就緒 | 可用的五模型接入、單一入口、真實觀測、scorer、結果目錄、失敗與續跑處理 | 已知正反例及代表性端到端路徑通過；紀錄／計時／分母可核對；必要安全檢查通過 | Agent 實作與 focused 驗證；使用者處理必要模型授權及適用的集中驗收 |
| M3 Pilot | 規格第 6 節的小規模真模型試跑、問題分類、成本與可行性報告 | M1／M2 均通過才開跑；可區分模型錯誤、產品故障與無效測量，能據以確認 M4–M6 預算 | Agent 執行／整理；使用者集中確認成本、速度目標與必要調整 |
| M4 Development | 保存的 B0、有限改善方案、B1／B2 候選及同題比較 | 規格第 6 節的中止與進入 Validation 清單通過；不以分數完美為出口 | Agent 推進已授權方案；使用者只處理契約、範圍或超預算決策 |
| M5 Validation 與凍結 | 固定候選的比較、選版理由、人工 scorer 核對與 Test 配置 | 選版規則先固定，評分可信；選定系統、B0、適用消融與分析方式凍結後才解封 Test | Agent 執行與整理；使用者人工核對、確認凍結並提供封存 Test |
| M6 Test 與論文結果 | 完整逐題結果、人工核對、表圖、失敗分析、限制與重現附件 | 承諾條件結果完整且無未解釋排除；每項論文主張能連到證據，不要求正向結果 | Agent 整理證據與結果草稿；使用者核對解釋與論文表述 |

### M1：先完成題目，不拿 pilot 代替出題

1. Agent 先提出工具／情境覆蓋表與一份共用題目模板：題號、family、split、使用者輸入、
   初始狀態、可用工具、允許的答案／參數、禁止副作用、預期觀測層與 fixture 身分。
   先以少量非 Test 人工題驗證模板與 oracle 可表達需求，再大量填題；不擴張工具契約。
2. 使用者協調自己／受邀者提供人工 seeds／改寫與語意核對；agent 先提供模板與格式檢查，
   Dev／Validation 的 AI 改寫須另行確認，不替代人工作者生成「全人工 Test」。
   先分 family 再改寫，不能事後隨機切分。
3. 正式題庫全數完成後核對語意、標準答案、數量與重複風險。Validation 不用來修產品或調 prompt；
   對其題目格式的必要準備不等於允許先看模型結果。Pilot 只抽已準備好的 Development 題目。
4. Test 由使用者在隔離位置完成審查與封存；agent 可提供本機檢查工具供使用者執行，
   只接收數量、版本／hash 與審查狀態，不接收題文、oracle、含題文 log 或實驗前的 Test 軌跡。
   這不能冒稱 agent 已獨立審過 Test 語意；單人出題／評分限制照實保留。

### M2：確認可測量與可運作，不要求模型先很準

#### M0 source 核對與 M2 最小準備範圍

以下為既有 source 接點盤點，不是 runtime 通過證據；施工權限以上方 active scope 為準：

| 現有接點 | 可重用部分 | M2 必須補齊／確認 |
| --- | --- | --- |
| `llm/action_contracts.py`、tools definitions、核准 target | 18 工具、schema、既有 owner 與確認／結果契約 | 逐工具情境與可觀測結果對應，不新增第二套 readiness |
| `scripts/dev/assistant_benchmark_calibration.py` | 真 parser／schema 的離線正反例模式 | 新研究 scorer 配合已確認的缺資訊不執行與 GUI 交接分層；不改寫舊 calibration 的歷史成績 |
| `scripts/dev/run_stable_assistant_model_eval.py` | 保存設定／模型輸出及既有評估接點 | 舊 runner 綁定 primary 與 frozen cases，會攔截工具執行；不能直接當五模型真實 outcome runner |
| `llm/core/backends/local.py` prompt capture | 實際 prompt、raw output、metadata | 接上 case／repeat／修復與事件因果鏈，完整報告不是單次 capture 就有 |
| 正常 ChatPanel／Host／ApplicationService 與既有 walkthrough | 真實操作、UI、狀態與確認 owner | 研究 fixture 下的觀測、隔離／重置與結果收集，不複製命令執行責任 |
| 產品 model allow-list／runtime | 既有兩個 Granite 的受控產品載入 | 五模型研究接入與其餘三模型精確 revision／相容性另設有界研究配置；不默默擴張產品 Settings 或關閉 allow-list |

直接相關差異在準備開始時須核對：`pipeline_state.py` 的 preprocessed 工具清單目前未列
`select_channels`，而核准 target 的 stage 說明允許它；先確認實際 publication，不能用文件
假定該情境可執行。此為 M2 覆蓋／修理候選，不在本次文件工作順手改產品；若只需研究先選
已一致的合法情境，不把未測的情境冒稱已通過。

研究 fixture 建議從可重現的合法資料狀態建立，分為空工作區、有資料／預處理、epochs、
設定完成、執行中及完成 run；用現有服務建構、在案例間重置，不讓前題副作用影響下題。
Agent 負責 fixture 與機器欄位；使用者不用手填 publication、generation token 或內部 ID。
Synthetic fixture 適合工程驗證，但真實產品 outcome 必須另外取得適用的真實來源與 Windows
原生 UI 證據；不新下載整套資料集，也不把模擬訓練終態或預寫 JSON 當成實際運算。

本輪不擴張 GUI、模型產品清單、公開工具或一般對話功能；研究所需的接入、紀錄、scorer 與
直接必要缺陷已納入上方有限授權，產品契約或可見 UI 改變仍另作決策。只做單回合主分數的提案，不等於允許省略取消／狀態一致性測試。
模型精確來源、大小／VRAM、既有 cache 與可寫輸出位置須在下載前唯讀盤點，交付一份資源方案；
目前沒有選定新儲存目錄、下載模型、刪 cache、安裝環境或新增正式 CLI。

#### 本輪已授權的實作順序

施工前重新讀 Git／source，沿用既有 Command、模型載入與 prompt capture 能力；
每個直接必要 slice 補上 call sites、具體驗證命令與回退邊界，不在文件中發明尚不存在的 CLI。

1. 先接題目格式、oracle 與 scorer 的正反例，涵蓋選對／選錯、參數錯、缺資訊、No-call、
   Host 擋住錯誤但模型仍判錯等情況；確認讀取錯誤能被辨識，而不是靜默漏題。
2. 接正常 Assistant／Host／Command 觀測路徑，使用研究 fixture 核對操作、GUI 交接、
   前後狀態、確認／取消與必要失敗路徑；不以攔截執行或捏造 UI 終態當作產品成功。
3. 補單一入口的選一／多個／全部條件、逐次輸出、計時、修復預算、失敗分類與彙整。
   驗證中斷不遺失已存證據、續跑不覆寫、不重送終態不明操作、設定不一致不混入同一 run。
4. 經資源與授權確認後，五模型分別做載入／固定暖機／少量非 Test smoke check；
   固定精確 revision／模板／runtime／生成設定，核對 RAG on 真有檢索、off 不檢索。
   不相容或 OOM 明列 blocker，不換模型冒充通過；不要求 smoke check 決策全部正確。
5. 以同一份保存軌跡核對輸入、raw output、事件、決策分數、產品 outcome 與時間；
   已知 parser／scorer、取消／安全、漏記／誤計時問題須修到能判斷結果，才可進入 pilot。

此處「系統就緒」只涵蓋研究所需的可運作／可測量能力與必要安全保護，不是全產品零缺陷。
UI 或公開工具契約變更仍須明確確認；需要產品 handoff 時遵守既有 workflow，不為每次純評測
改動都要求 GUI 手測。真模型 smoke check 也須有預先列明的有限案例與資源預算。

### M3–M6：用證據推進，不以分數好看才結束

- **Pilot 前保存基線**：M2 就緒時保存可追溯的準備版本。Pilot 若暴露須修的產品／配置問題，
  留下前後版本與原因；M4 第一個改善方案前固定可重跑的 B0，不事後拿新版冒充改善前基線。
- **Pilot 出口**：交付每模型／條件的可行性、測量缺陷、延遲／修復／失敗分布與成本估計。
  成本須含載入、操作、重試及實際排程開銷，不只用最快題估計整場。超預算或量測仍壞即為
  checkpoint，提出有範圍的修正／調整，不暗中把剩餘矩陣跑完。
- **Development 出口**：按既定輪數／方案預算與規格 gate 執行。五模型比較不能變成無限調參；
  未授權且無關的產品／架構問題列為後續，不阻擋已能可信測量的本輪研究。
- **Validation 入口與出口**：看結果前固定候選、共同預算、速度門檻、相近判準、統計與安全規則。
  使用保存軌跡做人工作業；若 scorer 有缺陷，一致重評受影響紀錄，不挑有利版本。
  完成選版與凍結後，不再依 Validation 追加改善方案。
- **Test 出口**：只跑規格批准的完整系統、適用消融與同模型 B0；原始軌跡可追到圖表。
  低分、負面消融或 B0 較好都照實報告，不據此重新選版／調參後混入同一獨立 Test。
  人工抽查、剩餘缺失與論文限制齊全，才宣稱本階段結果完成。

### 集中決策時點與分工

| 最晚決定時點 | 集中核對的內容 | 處理方式 |
| --- | --- | --- |
| M1／M2 開始前 | 研究問題表述、題目模板／覆蓋、fixture 與操作層範圍、實作／模型資源授權；多輪是否納入 | Agent 提供一包建議，使用者確認範圍；未批准的多輪數量不默認施工 |
| M3 開始前 | M1／M2 通過證據、精確五模型配置、pilot 題目清單／順序、smoke 與 pilot 資源範圍、輸出位置 | 不需要先決定最終模型贏家；不使用 Validation／Test 做 pilot |
| M3 完成後、M4 開始前 | 實測成本、剩餘人力、改善預算／截止日期、必要的技術配置調整 | 維持既定上限；需變更研究預算或範圍時一次確認，不自行延長 |
| M5 開始前 | 最終 Validation 矩陣、P95 門檻、相近／較簡單判準、統計算法與人工抽樣細則 | Agent 依 pilot／Dev 提出完整預設方案，使用者集中核對；不得看 Validation 後挑規則 |
| M6 解封前 | 選定系統、B0、適用消融、精確 source／設定／題庫／scorer 身分與執行清單 | 核對既定方法已落實，不再新增研究問題或依 Test 選有利分析 |

使用者協調自己／受邀者的人工出題，負責 Test 封存、必要條款與研究取捨、約定的人工核對及真正產品驗收；
agent 負責模板、非 Test 輔助工作、直接必要實作／驗證、紀錄與報告整理。
檔名、內部欄位、輸出排版等在既有契約內由 agent 提供一致預設，不逐項打斷使用者；
新下載、外部分享、破壞性清理、可見 UI／工具契約與實質預算擴張仍不是默認授權。

### 時程、風險與跨 context 接續

- 研究規格中的結果目標日與暫定改善截止日保留，但**尚無可行性證據，不是完成保證**。
  M1 要先完成整套題庫，受邀出題者及審查分工尚待確認；機器平行不能抵銷此人力依賴。
- M1 初批人工題完成後記錄實際出題／核對時間，估算剩餘工作；M2 盤點模型授權與接入缺口，
  M3 才有正式機器成本。據此在同一計畫排定可承諾的時程，不先替每個 milestone 填虛構日期。
- 若日期、完整題庫與可投入人力互相衝突，集中提出調日期／範圍的選項；不得縮題、改成 AI Test、
  降低驗證或自動增加人工負擔來假裝準時。未取得模型存取權也不能偷偷替代五模型。
- 每個 milestone 以具體交付與 gate 狀態回報；目前進度由上方 active 節擁有，
  文件更新不等於已通過題庫／runtime gate。施工只在已批准 scope 內持續，
  context compaction 或完成小切片不是停止或新授權的理由。
- 接手先讀上方 active、本節、研究規格、Git 與可辨識的執行狀態，再續作當前已授權項目；
  在 active 節更新進度、下一步與 blocker，不建立第二份工作日誌／控制平台。

下方是既有產品優先順序與候選背景，不覆蓋本輪授權至 Pilot 的範圍，也不授權本線施工其他候選。

## Agreed order — Import UI → Assistant evaluator → cleanup/refactoring

使用者於 2026-09-16 指定以上順序；Preprocess panel 暫不作為下一個優先施工項目。
Import 白框修正已於 2026-09-16 完成 Windows 局部手測，使用者回覆「沒問題了可以準備合併」。
接受的產品 source 為 `b052fd75`，與修正 commit `d0a8b435` 的產品內容相同；接受範圍見
[Current](../current.md)。PR／CI／合併狀態以 GitHub 與 Git 為準，不重啟已完成的修理。
使用者批准的 Benchmark 第一輪已有離線 calibration 實作，能力與限制見下節；
其餘 UI 改版、Assistant runtime repair 與重構尚未開始。

本輪要讓匯入操作更清楚、Assistant 評測結果可信，再依具體問題繼續降低程式複雜度。
不以籠統的「架構已乾淨」、行數下降或總分提高作為完成證明。

### 1. Import UI：後續調整先確認範圍

- 已接受的白框修正不再是 active slice；原生 first-frame 與 transient-window 回歸留在測試。
  修理／失敗／逐幀證據與合併批准隨該修正 PR 保留，不把施工日誌留作後續 dispatch。
- **待確認**：使用者實際想調整的步驟、畫面、文案與互動；先看目前 UI／截圖並列出問題，
  不預先認定整個 wizard 都要重做。
- **邊界**：以已合併的匯入能力為基準，保留 reviewed labels、無標籤選擇、subject/run 選取、
  確認與取消、資料一致性保護。支援格式或 EEG 語意改變必須另作決策。
- **施工前**：將確認過的可見變更、預期行為、非目標、既有 owner、驗證與回退方式寫回本節。
  沿用共用 Windows 環境與 PowerShell log 先提供 PR 前局部預覽；不把 PR／CI 當作開啟本機
  預覽的前置條件，也不把預覽通過當作正式 CI 或合併批准。後續具體 UI 變更仍待確認。
- **完成條件**：已同意的 UI 問題有實際 diff 與正常／失敗／取消路徑證據，Import 既有能力
  無回歸；同版本適用 CI、跨來源資料及 Windows native 畫面／操作檢查通過，再集中一次手測。
  不要求使用者重測全部 134 個資料集，也不把既有自動匯入證據當作新 UI 的驗收。

### 2. Assistant evaluator：先確認評測器是否判得準

- **本輪 scope-complete**：三決策／三層離線 calibration、合成正反例及 focused regression
  已完成；契約、入口與 claim boundary 見
  [Benchmark calibration](../validation/assistant_benchmark_calibration.md)。這不是整體 Benchmark
  完成，也未執行真模型或證明產品成功率。舊 evaluator、81 cases 與 gates 不變；Git／CI／合併
  狀態仍從實際 repository 取得，不因本機驗證通過宣稱已合併或 handoff-ready。
- **下一個候選**：正常 ChatPanel → Host → Command 路徑的真實 observation 收集與 scorer
  對照，先確認少量場景、來源與資源預算，再補齊 active plan；不自動啟動模型／prompt／RAG 改動。
  人工 seeds、family 隔離、Validation／Sealed 管理與同軌跡獨立人工評分仍未實作。
  正式研究已確認依產品完成契約區分「開窗」與「完成操作」；詳見研究規格。
  舊合成 calibration 不因此成為真實 GUI outcome 證據。
- **診斷順序**：由少量可重現案例核對輸入、預期行為、raw output、解析／admission、confirmation、
  command 執行、verification 與評分結果，分開 evaluator 誤判、模型行為錯誤與產品執行錯誤。
- **修理邊界**：先固定預期行為與判分規則，再修理有證據的案例／scorer／runner 問題；
  重用既有 Command truth 與驗證入口，不讓 evaluator 建立另一套 readiness 或假成功。
  工具名稱、參數、確認及可見結果等產品契約變更仍須另外確認。
- **證據品質**：選取與已知誤判直接相關的正確、錯誤及必要邊界案例；明列分母、失敗、skip、
  runner／scorer 及模型版本。舊 frozen 結果保持原身分；若判分規則需改，先批准、版本化並說明差異，
  不暗改舊分數、不刪失敗案例充當進步。必要的真模型執行先固定案例與資源預算。
- **後續整階段完成條件**：可重現的誤判已修正，已知正／反例能被正確區分，有實際執行證據與獨立檢查，
  並清楚列出仍屬 Assistant 本體的問題。Evaluator 可靠不等於 Assistant 已達 Stable。
  若未發現 evaluator 缺陷，記錄判分依據與真正問題，不為了這個階段而強行修改。
  若只改測試／評分工具且沒有產品行為變更，不另要求 GUI 手測。

### 3. 清理與重構：按已確認的模組問題施工

- 完成前兩階段後，依實際 diff、reachable callers 與 reviewer findings 決定第一個模組，
  不現在先宣告整個核心都要重寫，也不重新執行已結束的全面匯入盤點。
- 每個模組明列責任、入口、測試保護與刪除／保留理由；優先刪除確認未使用的能力與專屬測試，
  合併重複政策與狀態。大型檔案依責任處理，不以搬檔或降低單檔行數冒充改善。
- Production、tests 與 scripts 一起看；mock-heavy 測試是否移除須有更可靠的替代證據。
  檢查不必要的資料複製、重複掃描及等待，但不先承諾大幅加速。
- **完成條件**：通過 reviewer 對本次責任邊界、回歸風險、測試有效性及複雜度的審查，
  已承諾項目與必要驗證齊全，才交付整合版本；不以做完一個切片當作整階段完成。
  無關發現列為後續候選，不無限擴張本輪。

### 節奏與跨輪延續

本文件是唯一 active plan；每階段開始前補齊具體 scope／假設／驗證／stop condition，施工中更新
next step 與 blocker。小 commit 用於回退，review 依模組與風險安排，不因每個小切片就要求手測／merge。
有產品可見變更時，在同意的完整範圍驗證完成後集中手測；真正需要新決策或授權時明確停在該邊界。
Context compaction 不是完成條件：接手先讀本節、Git 與執行狀態，再繼續已授權的下一步。
優先順序不是全部實作的預先授權；也不自動啟動下方獨立的 Assistant runtime repair 候選。

## Closed baseline

Quality-baseline closure was accepted and merged via
[PR #140](https://github.com/hxin-an/XBrainLab/pull/140). Its implementation/evidence history stays in
Git/PR, not active dispatch. Known Assistant limitations below remain deferred.

Retained import was manually accepted and merged through
[PR #141](https://github.com/hxin-an/XBrainLab/pull/141) on 2026-09-16. Accepted source, bounded
coverage and known limitations belong to [Current](../current.md); required data/failure evidence
remains on E. The former task worktrees were removed; do not restart their completed campaigns.

## Deferred candidate — Assistant runtime reliability (not evaluator scope)

Goal: reliable selection and parameter-collection continuity with no unexpected workflow side effects.
LOC, static pass, literal prompt assertions or one improved score are not completion criteria.

1. **Mechanism audit before choosing a fix.** Trace baseline/retained failures from full rendered input/
   RAG through raw output, parser, capability/provenance, typed receipt, GUI terminal and visible response.
   Separate intent errors, missing clarification fields, invalid/stale admission and evaluator assumptions.
   Reproduce a bounded set through normal ChatPanel with real execution, using no patient data.
   No Host intent guessing or new model experiments in this diagnostic phase.
2. **Approve a repair boundary.** Select one evidence-backed hypothesis and existing owner. Explicitly
   decide behavior for unspecified/multiple actions, missing/partial values, correction/cancel and
   unavailable tools. Tool/schema/confirmation/visible-flow or model/RAG changes require separate
   approval; current source/tests do not ratify target. A larger model is neither proven necessary nor
   authorized. No generic evaluator platform, control plane or parallel state owner.
3. **Separate development and acceptance.** Keep frozen 81/scorer unchanged as regression evidence.
   Before implementation, define supplementary development cases and disjoint reviewer-owned holdout
   by failure family. Never tune on the holdout or shrink its denominator; disclose prior exposure to
   frozen cases. Reuse existing runners, review any necessary bounded extension, and agree a candidate/
   resource budget before execution. Do not repeatedly add two more prompt attempts after failure.
4. **Implement/review one coherent repair.** Prefer deletion/reuse; test failing observable behavior
   through actual owners, then passing behavior. Mock external inference only in unit tests; real-model/
   native evidence cannot substitute fake generation or preapproved GUI terminals. Independent reviewer
   checks mechanism, meaningful tests, complexity and scope, not only summary.
5. **One integrated acceptance.** Require 36/36 positive, 10/10 explicit origin, 5/5 missing guards,
   5/5 direct clarification admission, 24/24 product no-action and 7/7 clarification. Holdout must show
   zero unexpected execution/confirmation/navigation/mutation and correct authorized continuations.
   Separate raw-model/Host/product outcomes. Then same-source normal ChatPanel→GUI→Command journey,
   relevant cancel/stale cleanup, applicable CI and one final Windows GUI/English Assistant acceptance.
   No Stable/generalized-safety claim from bounded cases alone. Unsupported mechanism or exhausted
   budget means a documented decision checkpoint, not weaker gates or automatic extra prompt edits.

This runtime repair proposal is separate from the evaluator phase above; its promotion criteria do not
automatically become evaluator-repair gates or authorize product/model changes.
New implementation begins only after diagnostic outcome, scope and budget are approved.

其他候選方向見 [Roadmap](roadmap.md)；不宣稱 Assistant Stable 或零缺陷。
