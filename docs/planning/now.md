# XBrainLab Now

最後更新：`2026-11-06`

## Active — Saliency 的 Subject 檢視

### 問題、授權與基線

使用者已手測通過並同意合併 BIDS PR #164，已 squash merge 至 main
`555733128c00b637dc5735f66679632bc6b81729`。該 PR 的 24 個適用 checks 成功，
原 90164c40 資料／native evidence 保留；不把舊 head 的證據冒稱 merge commit 新測試。
本輪從此 main 建立 `feat/saliency-subject-view`。研究 checkout／使用者 settings.json 不改。

使用者確認現有 UI 沒有 Subject 選項，並明確授權新增。現況：Evaluator 保留按真實 class
分組的逐 trial attribution，Visualization 僅有 Fold／Run／Method／Class；render request
沒有 subject，圖表依 class 平均目前 split 的全部 trials，無法檢查同一模型下某個受試者。

Outcome：可選 All subjects 或該結果實際包含的一個 subject；同一 subject 的選擇一致作用於
Map、Spectrogram、Topomap、3D，明示 Test／Validation 來源與 trial 數。保留現有每 trial 等權
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
- UI 已批准增加 Subject 選項與必要資料來源／樣本數；保持既有風格與響應式控制列。

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

### Current / next

- PR #164 已合併；舊 worktree 已清理，驗證證據與使用者手測訓練結果保留於本機 ignored artifacts。
- Subject publisher／render identity／UI selector 已實作。Focused：backend／artifact／lifecycle
  112、實際四圖 renderer 7、UI／provenance／cache 152，共 271 passed；Ruff／format 通過。
- 獨立覆核抓到並修正 Spectrogram 跨 Subject 快取、缺 class render 結束未釋放 compute busy、
  首次 compute 後 Subject 仍 disabled 三個問題；都有先失敗後通過的直接行為測試。
- Windows 原生示例使用兩人合成 EEG、真實一 epoch EEGNet 與 Gradient；切人、四圖、空 class、
  還原 All、900／1100／1450 寬度已檢查。Qt widget 截圖不包含內嵌 GL，另核對 VTK 渲染影像。
  示例不是使用者真實資料驗收，也不代表歸因科學有效性。
- 下一步：開啟此版 Windows 示例供使用者確認新增 Subject 版面／互動；確認設計後依既有流程
  進入正式候選及該版本 CI／source-diverse／UI gates。新分支尚未完整 CI，不宣稱 handoff-ready。
- 合併 main CI `42172708389` 已 completed/success，包含 Linux、Windows／macOS lifecycle、
  原生啟動、公開多來源資料及 UI checks。這些是 main 證據，不代替 Subject feature 的驗證。
