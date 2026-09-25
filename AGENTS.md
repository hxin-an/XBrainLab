# XBrainLab Agent Guide

最後更新：`2026-09-24`

Repo 級不變量；產品、plan、gate 由 canonical source 擁有。

## 權威與讀取

按任務需要讀取，不預防性載入全部文件：

- `docs/current.md`：產品事實與宣稱界線。
- `docs/planning/now.md`：active priority 與 candidate。
- `docs/architecture/`、`docs/target/`：current 與 target boundary。
- `docs/validation/README.md`：evidence 與 claim contract。
- `.agents/README.md`：repo-local skills、workflows 與 model dispatch。
- `scripts/dev/handoff_gate_spec.py`：唯一 executable handoff gate registry。

新階段先讀active plan，再按任務查current/validation與Git/PR。版本、dirty/worktree以Git為準；
校準衝突文件。舊聊天與歷史批准不授權新source；缺環境／權限須明示。

Context compaction後依`.agents/README.md`續做，不因此停工等催促。

## 授權與 scope ceiling

使用者要求、明定 acceptance 與直接必要依賴定義 **scope ceiling**；review/評估不擴大授權。

- 回答、解釋、審查、診斷或規劃：唯讀診斷回報，未要求不實作。
- 修改、建立或修復：實作授權scope內最小coherent change及直接驗證。
- 未授權的外部寫入、破壞性操作、付費行為、public contract 決策或實質 scope 擴張：先取得確認。
- 改變使用者可見 layout、文案、互動、狀態或流程時，實作前必須先取得使用者明確確認。`XBrainLab/ui/`
  內維持 presentation 的修正照已授權 scope 實作，不重複確認。
- 依既有授權完成施工、驗證及 commit/push/PR，不重複詢問；未授權 PR 仍須確認。
- 使用者指令優先於 skill；若 skill 導致暫停，指出指令並先完成未受阻的授權工作。

Adjacent finding 只因重現 defect、破壞 contract、安全／資料損失或妨礙驗證而阻擋；
其餘最多三項 follow-up，不實作且不阻擋 scope-complete。

## Plan-first repair

Bug／feature／refactor實作前更新唯一active plan `docs/planning/now.md`：問題與證據、outcome、
scope／non-goals、假設、步驟、focused validation、stop condition及UI確認狀態。

施工更新next step/blocker；完成移除active slice，真實改變留在canonical authority。

跨PR public contract 先核准target，source/tests不等於核准。Assistant tools 的名稱、membership、
side effects、confirmation、visible results 都是 public contract。

## 產品與 Git 不變量

- `main` 是唯一產品基線；一條短 task branch 只承擔一個主要目標。
- UI、Assistant、scripts 共用 `ApplicationService / Command API`；不另建 state、capability 或 error policy。
- MCP executable surface 已退役；若未來重新啟用，必須另開 public contract／security decision。不恢復
  `Prep Gate`、`Repair Loop`、`AQ-*`、retired skills 或 legacy dispatch surfaces。
- 開始前讀 `git status --short --branch` 與 current branch，保留不是本 agent 產生的修改。
- Root `settings.json` 是使用者本機 runtime 設定；不得 stage、commit、revert、覆寫或隱藏。
- 禁止未經要求使用 `git reset --hard`、`git checkout --` 或廣泛清理。
- 合併一律經 PR；PR base 與 head SHA 必須精確對應，CI 及 non-skipped checks 必須
  `completed/success`。Missing、pending、stale、cancelled 或 failed 都 fail closed。
- Merge先通知；批准依`docs/validation/README.md`，完成即依 handoff workflow 清理 PR worktree／中間產物。

## 程式碼品質與複雜度

品質順序：正確可靠 → 責任與資料流清楚 → 消除不必要複雜度。行數、檔數、抽象數不是目標；
不得為縮碼犧牲資料一致性、錯誤／取消處理或可讀性，也不壓成難讀寫法。

成果回報按產品、測試／fixtures、腳本、文件、設定／其他列新增／刪除／淨行數與合計；註明
基準與範圍，含未追蹤新增檔。二進位另列檔數、不算行數。本切片與分支累積分開，不混入
既有修改；各類均說明審查／驗證與限制，不以production通過代表全部。

先檢查既有 owner 能否重用。Owner 掌管 admission、mutation/publication、confirmation 或
async lifecycle；DTO、parser、renderer、純函式不是 owner。

下列情況先做complexity review：列deletion candidates、owners before/after、production `+/-/net LOC`、
必要性與拆分方案；數量是審查訊號、非縮碼目標：

- Bug fix 淨增超過 300 production LOC、觸及超過 8 個 production files，或新增 production
  module/public class。
- Pure refactor 淨增超過 100 production LOC 或 owner 數增加。
- New feature 淨增超過 800 production LOC、觸及超過 12 個 production files，或增加超過
  1 個 owner。
- 任一 slice 超過 1,500 production LOC 必須拆 PR，或取得明確 architecture/user exception。
- 新增 authoritative owner、state machine、receipt 或 compatibility path 不看行數，一律觸發。

新abstraction須改善責任邊界、移除重複policy或隔離必要unsafe/external seam；caller數不單獨
決定是否值得抽象。Receipt只用於跨turn/process/TOCTOU/trust boundary；compatibility path須有
真實migration對象與移除條件。不建汎用complexity manifest或新control plane執行這些規則。

測試保護真實defect／行為／state transition／side effect，不複述helper。Source guard限穩定、
可靜態判定且會重複違反的規則。Canonical docs僅隨事實／決策／契約更新；不逐次測試建receipt，
不重複寫implementation log與worklog。

依`.agents/README.md`的獨立性、成本與風險判準分工，不設人數／角色配額。每次修改都review，
高風險獨立覆核；主agent可實作，但須驗收實際diff／證據，不能只信摘要。

## 驗證與完成語意

- `scope-complete`：使用者要求的 observable outcome 與直接相關驗證已完成。
- `checkpoint`：in-scope 行為或 evidence 仍缺少；不是停止條件，依handoff workflow繼續追蹤。
- `blocked`：需要新的使用者決策或本環境無法取得的必要資源。
- `handoff-ready`：只在 `.agents/workflows/handoff-candidate.md` 的所有 applicable gate 對同一
  clean/explained exact commit 通過後使用。

日常只驗直接相關範圍；交付證據依`docs/validation/README.md`。同PR head CI成功後不重跑
等價本機全套；完整manifest限明確的完整版本驗證需求。
可見變更仍需 changed-surface screenshot/walkthrough；deterministic widget/geometry/pixel checks
處理可機械判斷的事實，模型只審設計與異常。Offscreen 不取代 Windows native acceptance。
Data/import/label/epoch/training/evaluation/visualization 仍需同版本 source-diverse gate，可由 CI 提供。

## 資源與程序安全

- 產品 local model/revision 從 active decision 取得，不得 silent fallback。下載前確認來源、授權、
  quantization、大小、VRAM、cache 位置與清理方式；單模型原則不超過 10 GB，總 cache 不超過
  20 GB。27B+ 需明確授權，不使用中國公司／來源模型。
- Qt、PyTorch、MNE 或其他可能 native abort 的驗證使用 `prlimit --core=0` 與明確 timeout。
- 只能終止本 agent 明確啟動且可辨識的單一 PID/session。禁止 `wsl --shutdown`、system
  shutdown、`killall`、廣泛 `pkill` 或關閉無關程序。
