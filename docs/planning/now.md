# XBrainLab Now

最後更新：`2026-11-07`

## Active — 逐人分配的資料切分與移除 Manual

使用者於 2026-11-06 確認完整方案並授權實作；UI 選項收斂已批准。基線為
PR #165 的 d8a9e264；沿用目前 worktree，保留 Saliency 工作、使用者設定及已訓練結果。
審查已用真 MNE 合成 epochs 重現 Full Trial 只涵蓋少數人的偏斜、Individual Manual
不可用，以及簡單可行 Number 分割被貪婪搜尋拒絕。54 組正常矩陣通過不代表這些問題不存在。

### Outcome 與核准契約

- Trial / Session 先在每位受試者內切分；Full 合併同一 fold 的各人 masks，Individual
  各自保留。Subject 只在 Full 以整個人分配。Session identity 是 subject 內的 session，
  不再把不同人的同名 session 當作強制全域一組；BIDS run 不冒充 session。
- Test 先隔離，Validation 只取非 Test 資料。相同單位共同規劃，Test / Validation 的
  Ratio 都以原始 scope 計算；不同單位時 Validation 在 Test 留出後的剩餘 scope 計算。
  Trial Test 的 Val 只能 Disable / Trial；Session Test 可 Disable / Session / Trial；
  Subject Test 可 Disable / Subject / Session / Trial。逆向組合拒絕並要求重新設定。
- Number 是各 scope 的確切 group 數；Trial / Session 按每人計算，Subject 按全體人計算。
  Ratio 只做整數及不可拆 group 的取捨；不得搜尋相距很遠的新比例來湊成功。不足時指出
  subject / partition 原因，不跳過任何人。維持 train 所需 class、必要集合非空與 leakage gate。
- 保留原子時間重疊群組；類別分配以盡量維持來源比例為目標，不重採樣、不保證所有
  holdout classes 均存在。使用固定且有紀錄的 split seed，Preview / Train masks 必須一致。
- KFold 在上述 scope 產生 exact K、互斥且聯集完整的 Test；Full Trial / Session 合併各人
  同一折，Individual 為每人 K 折。Validation Disable / Ratio / Number。
- 徹底刪除 Manual 選項、enum / parser / allocator 分支、對話框及專屬測試。舊 Manual
  設定拒絕重新執行並提示重新設定，不能靜默改 Ratio；已保存結果仍可讀，不重新切分。

### Scope / complexity / 步驟

只處理 splitting、直接 Preview / admission / audit / saved configuration consumers、相關
UI / 測試 / fixtures / scripts / canonical docs；不改模型、Assistant tools、saliency 計算或
加入 solver / 通用框架。既有 DatasetGenerator、SplitAudit、ApplicationService 仍擁有原責任，
不新增 authoritative owner。優先刪 Manual 與舊比例回退，重用分配核心；必要純函式拆分
須有明確責任，不為行數切檔。施工超過原複雜度門檻時先重審實際 diff，不擴大 scope。

1. 先加五人 Trial / Session、混用規則、Number / KFold、失敗 atomicity 回歸並觀察舊版失敗。
2. 收斂 generator / contract / audit，UI 只消費同一 capability，刪 Manual 全鏈。
3. 遷移仍保護真行為的 fixtures / scripts；刪除僅屬退役功能的測試；舊結果讀取驗證。
4. focused backend / UI / integration、lint / typing；資料映射及 receipt 邊界獨立覆核。
5. Windows 原生展示新選項與五人 Preview；正式手測交付前完成同 head CI、source-diverse
   與適用 native / UI gates。使用者仍需手測並另同意 merge，不自動合併。

### Current / next / stop

逐人分配、允許組合、固定 seed 與 Manual 全鏈移除已實作；直接失敗基線已確認。
獨立覆核找到的高比例可行分割與 masks 記憶體問題已修正並補回歸；同／異單位的
類別比例與不等量受試者 KFold 也已補驗。最終覆核無 blocking finding，真實 CPU 訓練／
結果保存與 UI focused tests、lint／typing 通過。下一步為同版本 CI、Windows 原生
選項／實際五人資料驗證與正式手測啟動。Stop 為授權 outcome、直接驗證與獨立
覆核完成，適用正式 gates 通過後開 Windows 完整版本供一次集中手測；不以中途 commit、
CI pending 或 compaction 結束。未知平台／資料限制明列，原有 app / 結果不擅自關閉或清除。

## Pending acceptance — Saliency 的 Subject 檢視

### 問題、授權與基線

使用者已手測通過並同意合併 BIDS PR #164，已 squash merge 至 main
`555733128c00b637dc5735f66679632bc6b81729`。該 PR 的 24 個適用 checks 成功，
原 90164c40 資料／native evidence 保留；不把舊 head 的證據冒稱 merge commit 新測試。
本輪從此 main 建立 `feat/saliency-subject-view`。研究 checkout／使用者 settings.json 不改。

使用者確認現有 UI 沒有 Subject 選項，並明確授權新增。現況：Evaluator 保留按真實 class
分組的逐 trial attribution，Visualization 僅有 Fold／Run／Method／Class；render request
沒有 subject，圖表依 class 平均目前 split 的全部 trials，無法檢查同一模型下某個受試者。

Outcome：可選 All subjects 或該結果實際包含的一個 subject；同一 subject 的選擇一致作用於
Map、Spectrogram、Topomap、3D，後端保留 Test／Validation 來源與 trial 數，UI 不另顯示資訊列。保留現有每 trial 等權
的 All subjects 語意，不冒稱 subject 等權群體統計。切換只處理已計算結果，不重訓／重算歸因。

### Scope 與 non-goals

- 沿用現有 publisher 驗證／detached render data／owned render work／UI 控制；支援 exact run
  及已 admission 的 cross-fold Test cohort，維持 producer、publication、stale／cancel 邊界。
- 從已驗證 epoch／split／class 對應建立 subject 選項與篩選；不得靠 display name 或猜測順序。
  非完整／未知對應拒絕單人顯示，不靜默回退成全體；舊結果保留既有可讀能力。
- 未納入該結果的人不列選項。單人缺某 class 時可呈現無資料或僅可用類別，不能借用他人
  trials、崩潰或要求無意義重算。All subjects 原結果保持一致。
- 不改 split 策略、training、attribution 方法／目標、Test/Validation 選擇、模型／RAG、
  EEG／研究原始資料、Assistant 公開工具契約；不新增 trial selector 或群體統計政策。
- UI 已批准增加 Subject 選項；使用者要求移除額外資訊列，保持既有風格與響應式控制列。

### 步驟與責任

1. 先落此 plan，追查逐 trial 排序、split mask、subject map、class 分組及保存／重開路徑。
2. 新增真兩人、交錯 class／subject、不同 trial 數的失敗測試；同時保護 Test、Validation、
   cross-fold、單人缺 class、stale、原資料不變與 existing All 結果。
3. 以既有 SaliencyRenderPublisher 負責選項／篩選，renderer 消費 detached 已篩資料，UI 只傳
   選擇與顯示。不得在 UI 讀 live Epochs 或另建 policy／cache owner。
4. UI selector、窄版排版、subject 切換 request identity／取消過期 render、各圖的空資料狀態。
5. Windows 原生預覽與 focused behavior／geometry 檢查，展示可回應的候選；設計確認前不跑
   因每次 UI 迭代而重複的重型 gates。資料映射及 async 邊界獨立覆核，主 agent 核對實際 diff。
6. 本輪最終驗證沿既有 canonical gates／同 head CI；合併後全面測試需求仍保留，按最新
   使用者順序在已合併 main 上核對 Windows／Linux／macOS 自動證據並補缺口，無 Mac 實機
   不宣稱 native 手測。Subject 變更新版另需手測與 merge 批准。

### Complexity 與驗證

Owners before/after：既有 TrainingPlanHolder／EvalRecord 保留產出與完整性，既有
SaliencyRenderPublisher 保留資料解釋與 publication，既有 render work 保留 async lifecycle；
不新增 authoritative owner／state machine／receipt／compatibility path。
優先重用現有 class/mask/producer helpers；刪除候選為重複 filtering／selector refresh policy，
不移除安全檢查。若需拆大 renderer 的純計算 helper，先列必要性；超過 feature 800 net LOC、
12 product files 或新增 owner 時先 complexity review，不以縮碼犧牲來源對應。

Focused：saliency publisher、真實 evaluator→artifact→reload→render、四圖、控制列 geometry
與 rapid switching；Qt／MNE／Torch 使用 core=0 與 timeout，重型 native 串行。
可沿用同版本已成功 CI，不能把 mock/unit PASS 當 Windows 手測或科學歸因效度。
Stop：授權功能及直接驗證完成、獨立 review 無 blocking finding，Windows 候選可供使用者
檢查。不得自動合併新 feature。受限平台／缺少資料須明列，不能假裝全平台通過。

### UI 預覽修訂 — Subject 順序

使用者在原生預覽後明確要求 Subject 排在 Saliency 前面。只調整現有 responsive grid 的
排列為 Fold → Run → Subject → Saliency → Method；窄版第二列也先 Subject 再 Saliency。
不改資料篩選或計算。驗證控制項幾何／次序、focused UI tests 與 Windows 新截圖後更新
原生預覽。完成條件是各寬度皆維持要求的順序且無重疊；不因此重跑後端或重型 CI。
已完成：22 個排列／幾何 focused tests 通過；Windows 寬／中／窄原生截圖確認順序與無重疊。

### 正式驗證中的直接阻擋 — 高 DPI 圖表縮小

Subject 控制列的 Windows 150% capture 顯示控制項排列正常，但圖表被縮到左下方、標籤重疊。
追查既有 `fit_figure_subplots_to_canvas`：tightbbox 使用實體像素，canvas.get_width_height()
預設回傳邏輯像素，兩者在 DPR > 1 不一致。此 helper 未由 Subject 功能修改；本輪驗證才發現。
先用真實 Qt canvas 重現並對照主線 helper，確認不是截圖時序；若成立，只修正同一 helper
的像素單位，補高 DPI 幾何回歸及重新擷取受影響畫面。不重構 renderer／新增 owner，不放寬
檢查門檻；無高 DPI 副作用且 focused/native evidence 通過後，更新 PR 並以新 head 跑必要 CI。

### CI fixture 對齊

Linux integration-rest 的兩個 semantic label workflow 案例使用每類一筆的假 EvalRecord，
與已建立的實際 Test mask／順序不符，新的 Subject 對應檢查正確拒絕。只修正該 fixture，
使其 labels／outputs／逐類 saliency 行數符合真實 split，保留原標籤語意 assertions；
不放寬 production 檢查。先重現，再執行該檔的 focused tests，與 DPI 修正一起送新 head CI。

### CI UI 相容性補驗

同 head CI 發現 Spectrogram normalize 測試仍寫死舊 cache key、兩個 mock invalidation
案例可能混入 setup 的呼叫；逐項重現並以真實 reuse／失效邊界核對，不盲目放寬次數。
Linux 窄視窗要求 720px 卻被最小寬度撐至 723px；保持既有窄版可用範圍，調整直接相關
控制項的最小尺寸並驗證文字與幾何，不修改測試容許寬度。與既有 DPI／fixture 修復一起
獨立覆核後送新 head CI，直到所有適用 checks 成功再開正式手測。

### 手測 UI 修訂 — 移除圖表上方資訊行

使用者明確要求整行 `All subjects · Test · N trials · True class · Mean over EEG epochs`
小字移除。刪除該 QLabel、layout 項目與只為該行存在的組字／stale 清除機制，不能只隱藏留下
空白列。不改 Subject 篩選、結果資料、render identity、空 class 提示與原有分頁 tooltip。
先更新直接 UI assertions，以選中 subject／view property 驗證既有篩選與 trial 真值仍在；
執行 focused UI／排版測試與 lint，開 Windows 原生更新預覽。這是已授權的 UI 修訂，
先確認畫面，不把舊 head 綠燈當新版正式交付，不在每次文案迭代重跑重型 CI。
完成條件：資訊行與佔位完整移除，四圖選人／無資料狀態正常，更新畫面可供確認。
已完成此 UI 修訂：20 個 focused tests、lint／format 通過；Windows 寬／中／窄版預覽
已開啟且有回應。使用者現已要求「帶我手測準備 merge」，視為此 UI 定稿並重新進入正式交付。
下一步：提交此修訂，核對／必要時更新唯一受影響的 Visualization reference，不放寬門檻；
同 head CI 全部適用 gates 完成，補 Windows Subject 排版證據並更新正式啟動器與手測清單。
開啟完整程式與同一 console log，確認有回應後交付手測；不以此次準備要求自動合併。

### Current / next

- PR #164 已合併；舊 worktree 已清理，驗證證據與使用者手測訓練結果保留於本機 ignored artifacts。
- Subject publisher／render identity／UI selector 已實作。Focused：backend／artifact／lifecycle
  112、實際四圖 renderer 7、UI／provenance／cache 152，共 271 passed；Ruff／format 通過。
- 獨立覆核抓到並修正 Spectrogram 跨 Subject 快取、缺 class render 結束未釋放 compute busy、
  首次 compute 後 Subject 仍 disabled 三個問題；都有先失敗後通過的直接行為測試。
- Windows 原生示例使用兩人合成 EEG、真實一 epoch EEGNet 與 Gradient；切人、四圖、空 class、
  還原 All、900／1100／1450 寬度已檢查。Qt widget 截圖不包含內嵌 GL，另核對 VTK 渲染影像。
  示例不是使用者真實資料驗收，也不代表歸因科學有效性。
- 使用者已確認 Windows 示例並授權準備至合併前正式手測；Subject 順序定稿。
- 正式候選為 PR #165；核對同 head regression／static／source-diverse／跨平台／UI DPI gates；
  已依 CI exact-source 截圖與使用者確認版面更新唯一變動的 Visualization reference，
  保留原 drift 失敗證據且不放寬門檻。CI 已提供的同版本證據不重跑。
- 真實 A01/A02 GDF 已經過 Command 匯入／前處理／epochs、實際 EEGNet／Gradient、逐人
  篩選與安全結果重讀驗證；獨立 MNE event oracle 核對 274 epochs 與實際 Test rows。
  此補驗使用 domain 建立的受控 masks，不冒稱使用者點擊完整流程；同 head source-diverse CI
  另涵蓋多來源，Windows 手測仍待完成。
- 高 DPI 修正已獨立覆核；預設 CI 可跑的真 Agg 125%／150% 回歸先失敗再通過，
  QTAgg／Agg focused 共 11 passed。兩個 semantic fixture 已依實際 Test mask 修正，3 passed。
  UI setup mock 與 cache identity 修正：兩檔 104 passed，擴充後直接案例 8 passed；沒有放寬
  真實操作失效次數或 Subject／publication／training／run／method 快取隔離。
- 窄版最低尺寸已以實際 DejaVu 字型重現 722 > 720；Saliency 最小寬 120→115，
  保持原 720px gate、排列與字體。23 個直接幾何／Subject 測試通過，Linux 原平台由新 CI 核對。
- e0c0aef1 的 24 個適用 CI checks、Windows Subject 補驗及真實 A01/A02 路徑已通過。
  目前唯一後續產品改動為使用者要求移除資訊行；此修訂需新 head CI，不沿用舊 head 宣稱。
- 準備手測清單與綁定 candidate 的 Windows 完整程式
  啟動指令，隔離本機設定與輸出。全部適用 gates 完成才開正式手測，不以示例代替。
- 本輪 endpoint 為 handoff-ready 並已開啟完整程式；等待使用者實測及新的 merge 同意，
  此次不合併。研究 checkout／使用者 settings.json／既有結果保持不變。
- 合併 main CI `42172708389` 已 completed/success，包含 Linux、Windows／macOS lifecycle、
  原生啟動、公開多來源資料及 UI checks。這些是 main 證據，不代替 Subject feature 的驗證。
