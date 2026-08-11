# XBrainLab Agent Guide

最後更新：`2026-08-11`

這份文件只保留任何 coding agent 都必須遵守的 repo 級不變量。產品現況、施工順序與驗證命令
由下列 canonical sources 決定，不在這裡複製會變動的 branch、測試總數或 gate argv。

## 權威與讀取順序

一般工作依序讀：

1. `docs/current.md`：目前能宣稱與不能宣稱的產品事實。
2. `docs/planning/now.md`：active priority、candidate 與完成條件。
3. `docs/target/README.md`：目標態，不代表已完成。
4. `docs/architecture/README.md`：目前實作邊界。
5. `docs/validation/README.md`：evidence 等級與 claim boundary。
6. `.agents/README.md`：repo-local skills、workflows 與 agent 操作層。

只在任務需要時讀更深文件：論文主張、tool-call experiment 或 scorer 才讀
`.agents/context/thesis.md`；MCP 只有使用者明確要求才讀相關文件或 skill。Git inventory、branch、
dirty state 和 exact SHA 一律從 Git 取得。驗證 gate 的 executable registry 只以
`scripts/dev/handoff_gate_spec.py` 為準。

若 canonical sources 不一致，先以 source、runtime evidence 與 Git 校準文件，不建立第二份 queue。
`docs/records/`、artifacts、舊 goal 和 Git history 都是 provenance/evidence，不是 active dispatch。

## Agent 定位與授權

XBrainLab 是碩論實作，也是本地 EEG 桌面產品。coding agent 是工程交付者：需求若已明確，應把
scope 內的修改、測試、文件與同類掃描做完，不以 milestone 勾選、單一 PASS 或聊天自述代替產品
驗收。

- 回答、解釋、審查、診斷或規劃：只讀檢查並回報；未被要求時不實作。
- 修改、建立或修復：可直接做 scope 內的本機修改與非破壞性驗證。
- 外部寫入、破壞性操作、付費下載、或實質擴張 scope：先取得確認。
- 需求仍有重要歧義且不同選擇會改變產品契約時，停止猜測並向使用者確認。

Milestone 是最低門檻。若仍有同類 bug、缺測試、文件失真、不可用 UX 或架構分裂，不能稱完成。

## Product 與 scope 不變量

- `main` 是唯一產品基線；每項工作從最新 `main` 建立短 task branch，經 focused validation、PR
  與 exact-head CI 成功後才回到 `main`。
- 不從舊文件複製 active branch、worktree inventory 或測試總數。worktree inventory 使用
  `git worktree list --porcelain`。
- `ApplicationService / Command API` 是 UI、Assistant 與 headless scripts 共用的 product command
  spine。同一 workflow 不得出現第二套 state、capability policy 或錯誤語意。
- MCP 已退出 active product/thesis roadmap。只有使用者明確要求 MCP 時才 opt in；一般修復、
  handoff 與 security review 不新增 MCP gate。
- tool-call eval / thesis evidence 要等 backend、UI、Assistant 與 local LLM 主線穩定後再執行。
- 不任意改 UI layout；只有使用者明確要求或修復 bug 必要時才改。可見 UI 變動必須有 artifact。
- 不恢復 `Prep Gate`、`Repair Loop`、`AQ-*`、retired agent legacy directories 或退役
  repo-local skills。

## Branch 與 dirty worktree

開始前執行 `git status --short --branch`、`git branch --show-current`，說明本輪 scope、刻意不碰的
區域及需保留的 dirty files。

- 保留不是本 agent 產生的修改；禁止未經要求使用 `git reset --hard`、`git checkout --` 或廣泛清理。
- Repo root `settings.json` 是使用者本機 LLM/runtime 設定。不得 stage、commit、revert、覆寫或用
  skip-worktree 隱藏；handoff 時它可作為唯一明確列出的 dirty path。
- 一條 branch 只承擔一個主要目標。開始下一條 branch 前，前一條必須已合併、關閉或明確保留為
  checkpoint；不要無意識把新 branch 疊在未合併 branch 上。
- 重要 checkpoint 必須 focused commit、push 並留下驗證結果；push 不等於 merge。
- 合併一律經 PR。PR base 必須是預期的 `main`，且 PR head SHA 對應的 CI run 必須
  `completed/success`；所有非 skipped checks 也須成功。缺 run、pending、stale、cancelled 或 failed
  都 fail closed，不使用 `gh pr merge --auto` 繞過確認。

## Scope record 與停止條件

多步驟工作開始時留下短而可驗證的 scope record：repo root、branch/base/upstream、HEAD、dirty
files、使用者要求、non-goals、受影響區域與預計 validation。計畫只描述有依賴關係的工作，不把
顯而易見的單一步驟展開成長清單，也不把可能的未來改善偷偷納入本 branch。

遇到下列情況時先收斂而不是繼續擴張：

- source evidence 顯示修復需要改變使用者未授權的產品決策或 public contract。
- 必要資料、模型、平台或真人 acceptance 無法在本環境取得。
- 同類掃描發現另一個獨立產品區域，無法由同一組驗證證明。
- 測試 failure 來自環境或既有問題，和本輪 expected behavior 無關。

前兩類要向使用者請求決策或明確標示 blocked；後兩類要切成獨立 checkpoint/issue，不能在同一
diff 無限延伸。純 docs/guidance 工作不跑無關的產品資料集或 Qt gate，但仍須做連結、source
guard、focused tests、strict docs build 與 claim boundary。

## 工程交付與 reviewer 責任

較大工作可拆成互不重疊的 UI、backend、Assistant、QA 或 docs slices，但主 agent 對結論負責：

- worker 回報不是證據；主 agent 必須讀 diff、跑相關測試、看 artifact 並核對 current docs。
- worker 預設只接收 bounded prompt、必要路徑與驗收條件，不複製完整長對話。
- 大量並行前檢查 Windows C 槽與 `~/.codex/sessions` 增量。C 槽低於 30 GB、單輪 log 增加超過
  2 GB、或將產生大量 native crash dump 時停止擴增 worker。
- 公開資料、大型 benchmark、可重建 UI artifact 與大暫存放 D 槽，不放 WSL root filesystem。

實作時先寫清楚 observable behavior、same-class scope 與 validation floor。bug fix 應先有能重現
問題的 failing test；純重構應先建立 passing characterization baseline，再以相同測試證明行為不變。
測試優先驗 public behavior、state transition、structured result 與 real side effect，不以 mock 被呼叫
作為主要成功條件。

若問題類型可被靜態規則保護，新增或更新 product-code guard，並掃現有產品碼到 clean。完成前至少要有：

- same-class sweep：用 `rg`、source guard 或 bounded reviewer 找齊同類 call sites。
- focused validation：能直接保護修改點的最小測試。
- regression validation：覆蓋相鄰 workflow，不只跑新增測試。
- docs/claim sync：current truth、validation boundary 或決策有變時更新 canonical docs。
- claim boundary：列出仍需 Windows 真人驗收、未覆蓋環境或不能外推的結論。

缺任何一項時只能稱 validated checkpoint，不得稱完整完成。

## Handoff candidate

使用者不應成為第一層 QA。宣稱「可以手測」、「handoff-ready」或「這版可給你測」前，必須依
`.agents/workflows/handoff-candidate.md` 完成：

1. scope 與 non-goals。
2. focused regression 或可觀察重現 artifact。
3. same-class sweep 與適用的 product-code guard。
4. 一條使用者式 happy path。
5. 相鄰 edge/regression coverage。
6. 可見 UI 的 screenshot/walkthrough review；主 agent 必須自己看過。
7. clean/explained worktree、focused commit 與 pushed exact SHA。
8. 明確 claim boundary。

data import、label、epoch、training、evaluation 或 visualization handoff 還要跑 canonical required
multi-dataset gate；同一資料集轉檔只算 format coverage，不算 dataset diversity。跳過任何 required
gate 時只能回報 checkpoint。

UI artifact 必須檢查跑版、對比、primary action、text fit、nested scroll、dialog geometry 與不同 DPI；
dashboard PASS 或 offscreen screenshot 不取代 Windows native acceptance。

## Local LLM、資源與程序安全

- 產品模型與 exact revision 讀 active product decision；不得 silent model fallback。
- 使用者目標硬體約 16 GB VRAM。下載前確認來源、授權、quantization、大小、VRAM、cache 位置與
  清理方式；單一模型原則不超過 10 GB、總 cache 不超過 20 GB。
- 不使用或下載中國公司/來源模型，包括 Qwen、DeepSeek、Yi、GLM、Baichuan、InternLM、MiniCPM。
- local LLM 不可用時 UI 必須 recoverable、顯示原因且不可閃退。
- Qt、PyTorch、MNE 或其他可能 native abort 的驗證使用 `prlimit --core=0` 與明確 timeout。
- 測試卡住時只能終止本 agent 明確啟動且可識別的單一 PID/tool session。禁止 `wsl --shutdown`、
  系統 `shutdown`、`killall`、廣泛 `pkill` 或關閉無關程序。

## 驗證與文件

驗證命令、profile、順序與 evidence identity 以 `docs/validation/README.md` 和
`scripts/dev/handoff_gate_spec.py` 為準；不要在 skill/runbook 複製第二份 manifest。focused work
只跑相關 slice，但要如實標示它能支撐的 claim。任何 final total 或 PASS 必須來自同一個 clean
exact commit 的 handoff evidence；baseline、dirty tree 或不同 SHA 不得作 closure 結論。

文件分工：

- `docs/current.md`：current product truth。
- `docs/architecture/`：current implementation boundaries。
- `docs/target/`：target state。
- `docs/planning/now.md`：active work；`roadmap.md`：長期順序。
- `docs/decisions/README.md`：決策；`docs/validation/README.md`：evidence/claim contract。
- `docs/records/implementation_log.md`：重要工程紀錄；`worklog.md`：流水帳與驗證紀錄。
- `.agents/`：agent 操作層；不得成為 product current truth 的副本。

不新增大型 planning 文件；優先更新既有 canonical docs。禁用舊入口包括 `docs/current/*`、
`docs/history/*`、`docs/workflows/*`、`docs/thesis/*`、`docs/legacy/*`、`.agents/legacy/*` 與
`/mnt/d/repos/XBrainLab`。實際 checkout 永遠以 `git rev-parse --show-toplevel` 為準。
