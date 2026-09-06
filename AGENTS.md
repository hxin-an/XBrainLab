# XBrainLab Agent Guide

最後更新：`2026-09-07`

Repo 級不變量；產品、plan、gate 由 canonical source 擁有。

## 權威與讀取

一般任務按需要讀取，不為了預防性審查把全部文件載入：

- `docs/current.md`：目前能與不能宣稱的產品事實。
- `docs/planning/now.md`：active priority 與 candidate。
- `docs/architecture/`、`docs/target/`：current 與 target boundary。
- `docs/validation/README.md`：evidence 與 claim contract。
- `.agents/README.md`：repo-local skills、workflows 與 model dispatch。
- `scripts/dev/handoff_gate_spec.py`：唯一 executable handoff gate registry。

Git identity、branch、dirty state與worktree inventory從Git取得。文件與source/runtime/Git衝突時校準
canonical doc；records/artifacts是歷史，不作active dispatch。

## 授權與 scope ceiling

使用者要求、明定 acceptance 與直接必要依賴定義 **scope ceiling**；review/評估不擴大授權。

- 回答、解釋、審查、診斷或規劃：唯讀診斷並回報，未被要求時不實作。
- 修改、建立或修復：實作授權 scope 內的最小 coherent change 與直接驗證。
- 未授權的外部寫入、破壞性操作、付費行為、public contract 決策或實質 scope 擴張：先取得確認。
- 改變使用者可見 layout、文案、互動、狀態或流程時，實作前必須先取得使用者明確確認。`XBrainLab/ui/`
  內維持 presentation 的修正照已授權 scope 實作，不重複確認。
- 已授權 scope 內完成必要工作、focused validation、commit/push/PR。不重複詢問既有授權；未授權 PR
  仍須確認，merge 規則不變。
- 使用者指令優先於 skill；若 skill 導致暫停，指出指令並先完成未受阻的授權工作。

只有重現 defect、破壞 contract、造成安全／資料損失或令 focused validation 無法判斷的 adjacent finding
阻擋本 slice。其他最多三項 follow-up，不實作且不影響 scope-complete。

## Plan-first repair

Product bug、feature或refactor開始實作前先更新唯一active plan `docs/planning/now.md`，涵蓋問題與證據、
outcome、scope／non-goals、假設、修理步驟、focused validation、stop condition與UI確認狀態。

施工中更新 next step/blocker；完成後移除 active slice，只把真實改變留在 canonical authority。

Multi-PR public contracts require approved decisions/target before implementation; current source/tests
never ratify target. Assistant tool names, membership, side effects, confirmation, and visible results are
public contracts.

## 產品與 Git 不變量

- `main` 是唯一產品基線；一條短 task branch 只承擔一個主要目標。
- `ApplicationService / Command API` 是 UI、Assistant 與 scripts 共用的 command spine；同一
  workflow 不得建立第二套 state、capability policy 或 error semantics。
- MCP executable surface 已退役；若未來重新啟用，必須另開 public contract／security decision。不恢復
  `Prep Gate`、`Repair Loop`、`AQ-*`、retired skills 或 legacy dispatch surfaces。
- 開始前讀 `git status --short --branch` 與 current branch，保留不是本 agent 產生的修改。
- Root `settings.json` 是使用者本機 runtime 設定；不得 stage、commit、revert、覆寫或隱藏。
- 禁止未經要求使用 `git reset --hard`、`git checkout --` 或廣泛清理。
- 合併一律經 PR；PR base 與 head SHA 必須精確對應，CI 及 non-skipped checks 必須
  `completed/success`。Missing、pending、stale、cancelled 或 failed 都 fail closed。
- Product 行為只能在使用者明確表示手測通過並同意 merge 後合併；PR 的 `Manual acceptance`
  記錄日期、範圍與 source。Source 再改即失效；自動證據不取代批准。純 docs/tests/CI/guidance 可豁免。

## 複雜度與刪除優先

既有 owner 能表達行為時，bug fix 與 refactor 預設 deletion/reuse first。Owner 指能獨立決定
admission、authoritative mutation/publication、confirmation authority 或 async lifecycle 的
component；DTO、parser、renderer 和純函式不是 owner。

下列情況觸發 complexity review，必須在繼續前說明 deletion candidates、owners before/after、
production `+/-/net LOC`、必要性與拆分方案：

- Bug fix 淨增超過 300 production LOC、觸及超過 8 個 production files，或新增 production
  module/public class。
- Pure refactor 淨增超過 100 production LOC 或 owner 數增加。
- New feature 淨增超過 800 production LOC、觸及超過 12 個 production files，或增加超過
  1 個 owner。
- 任一 slice 超過 1,500 production LOC 必須拆 PR，或取得明確 architecture/user exception。
- 新增 authoritative owner、state machine、receipt 或 compatibility path 不看行數，一律觸發。

新 abstraction 只能服務至少兩個真實 production callers 或必要 unsafe/external seam，並在同一 diff
移除重複 policy。Receipt 只用於跨 turn/process/TOCTOU/trust boundary；compatibility path 必須有
真實 migration 對象與移除條件。不建立汎用 complexity manifest 或新 control plane 來執行這些規則。

測試對應 reachable defect、observable behavior、state transition 或 real side effect；不逐 helper 複製
implementation。只在規則穩定、可靜態描述且有重複風險時加 source guard。只在 current
truth、decision、architecture 或 evidence contract 真正改變時更新 canonical docs；不為每個
focused run 建 receipt 或同時寫 implementation log 與 worklog。

只在 independent、可平行且能節省時間或提升證據品質的 stream，或使用者明確要求協作時派 subagent。
單一 workflow 且不超過 8 個 production files 時預設不派；一般最多兩個互不重疊 worker，不重複同維度 review。

## 驗證與完成語意

- `scope-complete`：使用者要求的 observable outcome 與直接相關驗證已完成。
- `checkpoint`：明定的 in-scope 行為或必要 evidence 仍缺少。
- `blocked`：需要新的使用者決策或本環境無法取得的必要資源。
- `handoff-ready`：只在 `.agents/workflows/handoff-candidate.md` 的所有 applicable gate 對同一
  clean/explained exact commit 通過後使用。

日常只跑直接相關 focused checks；交付依 `docs/validation/README.md` 選 applicable evidence，
同一 PR head 已成功的 CI 不在本機重跑等價全套。完整 manifest 只供明確的完整版本驗證需求。
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
