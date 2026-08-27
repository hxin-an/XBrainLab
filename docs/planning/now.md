# XBrainLab Now

最後更新：`2026-08-28`

## 目前焦點

產品 source baseline 是 `52fa5a005045169cc38dc15f8990bff2b5440310`；本 plan 經 docs-only PR
合併後，三條 lane 必須從 post-plan `main` 的同一 exact SHA 建立隔離 worktree，同步改善 Data
Import 延遲、Assistant 多輪補參數能力，以及過度防禦／過度設計。主 agent 只負責協調、scope
gate、review adjudication、exact evidence、PR／CI 與手測交付；lane 的診斷與施工由 subagent
執行。

這是唯一 active implementation plan。三條 lane 不共用 production file，不互相 cherry-pick，
也不從彼此的未合併 branch 建立基線。

## 問題與既有證據

### Import discovery

- OpenNeuro ds003061 `sub-001` 在 WSL `/mnt/d` 的 candidate blocking median 為
  `12.046162s`，background median 為 `1.530436s`，stable-idle median 為 `13.558181s`；
  10 秒 gate 未通過。
- exact `31b79daf` audit 顯示 Review 約 `4.6s`，包含 241 次 `resolve`、627 次 `stat`；
  repeated `/mnt/d` `lstat` 是 dominant cost。
- review/apply/open 是不同 trust boundary。Apply final full rehash、`SourceFileBoundary`、symlink／
  containment 與 admitted materialization 必須保留；可刪的是同一 admission window 內高成本、
  低風險、沒有新增安全語意的重複 micro-race 檢查。

### Assistant effect

- 現行版本已比原始 2B baseline 明顯改善，但在「先要求補參數、下一輪使用者補齊」的第二、
  三輪仍常不執行；只做 prompt-only 兩輪迭代，成功機率不足。
- 目前 typed clarification receipt 只在模型輸出精確 typed clarification 時建立；raw model action、
  host interpretation 與 final outcome 必須分開量測，避免 evaluator 把 host rescue 誤算成模型能力。
- 產品可以保留模型已選定的 tool 與使用者／verifier 明確提供的值，但 host 不得自行推導另一個
  tool。Assistant tool 名稱、membership、side effect、confirmation 與 visible result 是 public
  contract，本 campaign 不改它們。

### Defensive complexity

- 測試與 production 都可能存在已不可達、只複製 implementation、或為極低機率情境付出高維護／
  runtime 成本的 guard；但低成本且防止真實檔案替換、資料遺失或 trust-boundary 破壞的 guard
  不是刪除目標。
- 具體 candidate 不在 plan 階段預判。Cleanup worktree 建立後才由 worker 蒐證，交由 contract
  challenger 判斷保護的 contract，再由主 agent 裁決並由獨立 reviewer 複核。

## 預期 outcome

1. Import：在不弱化 review/apply/open、TOCTOU、symlink／containment 與 final rehash 的前提下，
   刪除重複 discovery work；同一 benchmark median 至少改善 `0.5s`，production net LOC 必須為負。
2. Assistant：完成一個整合 candidate，使多輪補參數可累積且在值完整時執行既有 tool；不增加
   public tool contract、owner、router 或 state machine，並以固定 evaluator 分離 raw／host／final。
3. Cleanup：以刪除優先移除一個或多個有證據的同 subsystem guard family；不為了縮短程式碼而
   移除 reachable safety、資料完整性或使用者可觀察 contract。

## Scope 與 non-goals

### Import lane — `perf/import-discovery-deletion-v2`

- 最多觸及 2 個 production files；以 deletion／reuse 為預設。
- 保留 review/apply/open 邊界、admitted metadata 規則、final full rehash、symlink／containment。
- 不改 import UI、文案、資料解讀語意、BIDS mapping 或 public command contract。
- 若無法在上述限制下達到 `0.5s` median improvement，停止並回報 checkpoint，不擴張 scope。

### Assistant lane — `fix/assistant-effect-iteration-v2`

- 可改 prompt/context、few-shot examples、typed pending state、parser recovery、verifier、admission、
  retry 與 evaluator；最多 8 個 production files，bug-fix production net LOC 不得超過 `+300`。
- 最多驗證三個有清楚假設的 local commits：prompt/examples、receipt/admission、retry/context。
  最終 PR 只保留有 evidence 的 coherent 組合。
- 不新增 public tool、不改 tool side effect／confirmation、不 silent fallback、不新增 authoritative
  owner、router 或 state machine。觸發任一項即停止，回到 architecture／user decision。
- 不為追求分數由 host 猜 tool；只允許延續模型已選 tool，並累積使用者或 verifier 已證明的值。

### Cleanup lane — `refactor/overdefense-cleanup-v1`

- worktree 建立後才 discovery；每個 candidate 都記錄 reachable path、protected contract、成本、
  owner 與刪除後可觀察差異。
- 一個 local commit 只處理一個 guard family；同一 subsystem 的 coherent families 可合併成一個 PR。
- pure refactor production net LOC 必須小於等於 0，owner 數不得增加；不建立新 control plane、
  manifest、receipt 或 compatibility path。
- 純 tests／static checker／unreachable code 不要求無意義的 UI 手測。若 candidate 其實保護 reachable
  product behavior，移交 owning product lane，並要求相應使用者驗收。

### 全 campaign non-goals

- 不同時處理新的 UI layout／文案、中文輸入、electrode layout、模型下載或 model catalog。
- 不清除 root `settings.json`、模型 cache、資料集、系統 temp 或無法證明屬於 XBrainLab 的檔案。
- 不將既有未知 finding 塞進本 campaign；非直接 blocker 最多列三項 follow-up。

## 執行與 reviewer 拓樸

1. 主 agent 凍結 `main` exact SHA，建立三個獨立 worktree，宣告 production file ownership。
2. 三名 worker 可平行診斷／施工；每名 worker 先建立可重現 baseline，再提出最小 patch。
3. Import worker 以 performance measurement 自證；Assistant worker 以固定 evaluator 自證；Cleanup
   worker 對 candidate 建立 evidence packet，不自行判定 safety contract 可刪。
4. worker 完成後釋放 agent slot，依序啟用 reviewer：
   - Import：performance/resource reviewer + main agent boundary review。
   - Assistant：tool-call designer + test-quality reviewer；必要時 security/privacy review。
   - Cleanup：contract challenger 後再由獨立 code reviewer 複核主 agent 裁決。
5. 主 agent 只接受 exact clean/explained commit 的 evidence，負責 scope、diff、owner、production
   `+/-/net LOC`、CI 與 regression adjudication。review finding 不自動擴大 scope。
6. 每條 lane 各自走 PR；main 每次合併後，其餘 lane 必須同步最新 main 並重跑受影響 focused gate，
   不因 PR 很短而拆成重複的小 PR。

## Focused validation 與 stop condition

### Import

- 同一 source、mount、warm-up 與 fresh-service protocol 重跑 baseline/candidate；保存 raw timings。
- gate：candidate blocking median 至少快 `0.5s`，focused import/BIDS/symlink/containment tests 全過，
  production net LOC < 0，最多 2 個 production files。
- 任一 trust boundary 弱化、benchmark 不可重現或改善不足即停止，不宣稱成功。

### Assistant

- evaluator 必須先以獨立 local commit 固定，之後 hypothesis commits 不可修改 scorer 來追分。
- candidate gate：core `36/36`、explicit-origin `10/10`、missing guard `5/5`、clarification 至少
  `4/7`、current-target unexpected unsafe 小於等於 `2`；另通過一個中文與一個英文 partial
  accumulation trajectory。
- raw model、host rescue 與 final executed outcome 分開報告。任一核心 guard regression、unsafe
  action 上升、scope ceiling 觸發或無法在三個 hypothesis 內改善即停止。

### Cleanup

- 每個刪除先有 passing characterization baseline，或證明程式碼不可達／測試不觀察真實 behavior。
- 執行 owner subsystem 的 focused tests、Ruff、diff check，並由 reviewer 檢查 regression、lifecycle、
  data integrity 與 maintenance value。
- contract 無法說清、刪除後仍需新 abstraction 補洞、production LOC 淨增或 owner 增加即拒絕。

## 手測與完成語意

- Import 與 Assistant 會改 reachable product behavior，只有 exact source 完成 CI、WSLg walkthrough、
  使用者明確表示手測通過並同意 merge，才可合併。
- Cleanup 若只改 pure tests／static checker／不可達 code，可依 repo 豁免 human manual；若觸及
  reachable product behavior，必須提供有意義的 product walkthrough，不以「看不出差異」代替。
- lane 可分別達到 `scope-complete`；只有所有 applicable handoff gate 對同一 exact commit 成功時
  才稱 `handoff-ready`。缺 evidence 是 checkpoint，需要新決策才是 blocked。

## Campaign 收尾

三條 lane 完成或明確停在 checkpoint 後，移除本 active slice；只把真正改變的 current truth、
architecture decision 或 evidence contract 校準到其 canonical authority。合併後刪除 task worktree、
local／remote branch 與明確 XBrainLab-owned temp artifacts，確認 `main` 是唯一產品基線並保留使用者的
root `settings.json`。
