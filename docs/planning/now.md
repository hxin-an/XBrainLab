# XBrainLab Now

最後更新：`2026-08-13`

這頁只保存 active delivery context、近期施工順序和 exit condition。舊
[Product Quality Audit](../records/product_quality_audit_2026-07-30.md) 保留為此次 main checkpoint
的歷史 ledger，不再作為新的 active queue。

## 目前焦點

**以最新 `main` 為產品基線，先關閉固定 15-dataset MOABB BIDS / MainWindow reliability
candidate，再繼續效能與簡化 Assistant prototype。**

目前不是 release、Assistant-ready 或 Windows handoff candidate。真人資料驗收仍只涵蓋 Graz 2a
GDF 與 OpenNeuro ds003061 P300 BIDS 各一個資料集；新 15-dataset plan 的 materialization freeze
已完成。這一輪只有在固定 15 個 datasets 都以同一 clean exact commit / Poetry / CUDA /
checksum identity 各完成 cold + replay，共 30 條 fresh-process MainWindow journeys，且 exact-head
CI 成功後，才可形成 Windows 人工手測候選。另一個 20-scenario gate 仍是分開的 pending scope，
不能與這 30 條 journeys 互相冒充。

## Active Delivery Context

| 項目 | Current value |
| --- | --- |
| Worktree | 以 `git rev-parse --show-toplevel`、`git branch --show-current` 與 `git status --short --branch` 為準。 |
| Product baseline | `main` |
| Candidate branch | 從最新 `main` 建立的短 task branch；實際 branch / SHA 從 Git 取得，不在 canonical plan 寫死。 |
| Baseline | 以當次 `main` / merge-base 為準，不重用舊 SHA。 |
| Goal | 固定 15-dataset GUI reliability closure；其後才是 performance 與 simplified Assistant prototype。 |
| Historical ledger | [Product Quality Audit - 2026-07-30](../records/product_quality_audit_2026-07-30.md) |
| Current classification | dirty implementation checkpoint；15-dataset materialization、30 journeys、exact-head CI / Windows acceptance pending；not handoff-ready / not release / not Assistant-ready |

不要從舊文件推論 registered worktree 數量。需要 inventory 時執行
`git worktree list --porcelain`；其他 worktree 不得被誤認成 active candidate，也不得覆寫其
owner 的 dirty changes。

## Data / Training 目前交付邊界

本輪 BIDS label-field recommendation 必須來自 selected runs 的 bounded evidence：欄位存在與非空
coverage、觀察值、sidecar `Levels` 和跨 run consistency；若任一 selected table 的 row / byte
inspection 被截斷，或 evidence 不足，就不自動推薦，使用者明確選擇仍優先。Epoch context 只接受 reviewed import handoff 與對應 recording hints；handoff
缺少、格式錯誤、讀取失敗、source / placement 不一致，或 selected recordings 的 sampling frequency
不一致時 fail closed 且不改變既有資料。將所有 recordings resample 到同一 sampling frequency 後，
`Create Epoch` readiness 會恢復。Duration / event-locked
mode 也必須從這份 reviewed handoff 綁定的 placement / duration evidence 產生，不能由 UI fallback
猜測。

Data Splitting preview 會暫時建立 candidate datasets / masks 以計算摘要，然後恢復原狀。Confirm
先驗證 preview receipt，再只保存 lightweight typed specification、epoch revision、fingerprint 與
bounded preview summary，不發布 masks 或 training tensors。`Start Training` 才 authoritative
rematerialize datasets、執行 leakage / coverage audit、發布結果並進入 resource preflight；失敗時保留
既有 dataset / trainer / training state，不得因確認新設定先做 destructive cleanup。

本輪 Training 只實作當前已選模型的 deterministic recommended defaults，不實作計時
hyperparameter search、trial orchestration 或自動模型選擇。推薦值更新必須逐欄位處理：只更新未被
使用者編輯的欄位，並以 trusted host provenance 保留每一個已被使用者修改的值，不得因重新計算
recommendations 而整組覆寫。Recommendation 是保守 starting point；`Start Training` 的 resource
preflight 仍是最後 authority。

Training terminal publication 只提交 metrics，不得自動啟動 attribution。使用者必須在
Visualization 明確點擊 `Compute Saliency`；其 operation ID、dataset / run / split identity 與
terminal publication 必須一致，Map 與 Spectrogram 才能成為成功 receipt。Import review / apply、
preprocess、epoch、training、evaluation、saliency 與 render 的長工作共用 backend-owned operation
truth；Cancel / Stop / Close 不得排在 shared command lock 後面，取消後必須可在同一產品流程重試。

未來的計時搜尋必須依 [Roadmap](roadmap.md) 的 deferred contract 獨立交付；它不是本輪
candidate 的完成條件，也不可由現有 recommended-defaults UI 暗示為已有功能。

## 施工順序

| 順序 | 工作 | Exit signal |
| --- | --- | --- |
| 1 | Converge product reliability code | 關閉 BIDS index/cache、detached prepare / short commit、owned-work cancel/retry/close、explicit Saliency、Model Summary 與 Training resource preview 的 focused + adjacent regression；production code 不含 dataset-name branch。 |
| 2 | Freeze the 15-dataset matrix | D 槽 source / formal BIDS bytes、license、subjects、oracle、source + BIDS checksums、Poetry lock、CUDA/GPU 與 validator receipt 全部 pinned；tracked plan 從 awaiting materialization 產生可驗證 ready plan。 |
| 3 | Run 30 GUI journeys serially | 每個 dataset 各一個 cold / replay fresh process，只經 visible + enabled production controls 與 `QFileDialog` path boundary；5/5/5 cancellation partitions 都取消後重試成功。 |
| 4 | Review exact artifacts | 每條 journey 的 stages、classes/events、finite metrics、producer identity、Map、Spectrogram、timing、screenshots 與 clean close receipt 全部綠；主 agent 逐圖檢查，另完成與 exact plan/receipt/screenshot SHA 綁定的 independent visual-review attestation。 |
| 5 | Candidate gate and CI | 在同一 clean exact commit 跑 canonical handoff gates，commit/push/PR 後確認 exact-head CI completed/success；任一 dataset 或 gate 失敗即停止 handoff claim。 |
| 6 | Windows human boundary | 自動化 closure 後才進行 Windows native DPI / interaction / optional native 3D acceptance；它不回填為 Linux/offscreen evidence。 |
| 7 | Deferred product work | Performance measurement、simplified Assistant、Agent gate recalibration 與長期約 80-case MOABB expansion 從更新後的 `main` 分開施工。 |

## Active Reliability Closure TODO

這是本輪唯一 active TODO。Assistant、user-facing site、tool-call showcase、一般性 test cleanup
與長期約 80-case expansion 依 [Roadmap](roadmap.md) 延後，不在本表維護第二套狀態。
完成一列代表 exit signal 已有可重跑 evidence，不是 worker 回報「已實作」。

| Workstream | Required outcome | Exit signal | Status |
| --- | --- | --- | --- |
| BIDS discovery / interpretation | Formal BIDS root、nested root、subjects、recordings、sidecars、metadata、events 與 montage discovery 共用 backend index / content cache；不得新增 dataset-name production branch。 | Index/cache freshness、nested-root、selected-scope、sidecar replacement、bounded resource、same-class source guard 與 adjacent import tests 通過。 | Implementation checkpoint; combined review pending |
| Owned work / transactions | Import review/apply、preprocess、epoch、training、evaluation、saliency、render、Model Summary 與 Training preview 的重工作離開 Qt thread / long-held command lock；Cancel / Stop / Close 有 operation identity、retry 與 stale-result guard。 | Lock-independent control-path timing、cancel-before/after-commit、rollback、retry、close worker/subprocess inventory 與 freeze stress 通過。 | Focused dirty-tree tests passed; exact-source closure pending |
| Dataset materialization | 固定 15 rows 的 source/license/revision、subjects、formal BIDS root、validator、source + BIDS checksums、oracles、Poetry/CUDA/GPU identity 全部凍結在 D 槽。 | 15/15 ready rows；no-download replay 重新驗證相同 bytes，manifest denominator 不可替換。 | 15/15 ready；generated freeze / ready plan sealed，final-commit reseal仍由 candidate gate重驗 |
| MOABB GUI journeys | 固定 15 datasets / 30 cold+replay fresh processes，依序完成 Import BIDS -> subjects -> review/match -> apply -> preprocess -> epoch -> split -> model -> 1x1x1 training -> evaluation -> explicit Saliency -> Map -> Spectrogram -> close。 | 30/30 green receipts；runner 只允許 `QFileDialog` path injection，且 5/5/5 cancellation partitions 各覆蓋兩個 target stages並重試成功。 | 0 qualifying receipts |
| Journey evidence | 每個 dataset 只收錄實際 cold/replay 的 screenshots、stage timings、UI options、class/event、training/evaluation/saliency result、close outcome 與 limitation，不把 format coverage 冒充 dataset diversity。 | Machine-readable receipt 與人工 checklist 都能回指 exact data/source/process artifacts；主 agent 逐圖檢查。 | Pending real campaign |
| Integration and review | 保留目前手測衍生的 in-scope dirty fixes並收斂成 focused commits；不混入 Assistant/site/長期 campaign 工作。 | 主 agent 重讀完整 diff、跑 combined tests與 canonical handoff manifest、reviewer 重審，再從最新 `main` 形成 pushed PR exact head，所有 CI checks completed/success。 | Pending source closure |

分支邊界：實際 task branch / SHA 以 Git 與 PR pushed head 為準，不在本頁保存 mutable 名稱。
本輪只收斂 15-dataset reliability 所需的 backend、GUI、materializer、runner、tests、canonical
docs 與 evidence；Assistant contract、tool-call showcase、user-facing site 與長期約 80-case
expansion 不得趁收尾繼續擴張。後續工作從更新後的 `main` 建立短分支，不得把未審查 worker
commit 混入本 PR。

## Evidence Rule

本候選的 immediate exit signal 是：15 個 frozen BIDS datasets 與 checksums、30/30 qualifying
MainWindow receipts、populated Evaluation / explicit Saliency Map / Spectrogram artifacts、
same-class + focused + adjacent regression、required multi-dataset、strict docs/static、configured
upstream 與 exact-head CI 全部可追溯到同一 clean commit。現有 tracked screenshots、synthetic
receipts 或 runner unit tests 只能支撐 implementation checkpoint。

Final totals 不能從本頁、聊天、checkpoint notes 或多次局部 pytest output 手動加總。
唯一可用的 final totals 是同一 clean exact commit 產生的 handoff evidence，且至少要記錄：

- profile；
- worktree / branch；
- full commit SHA；
- dirty / protected-local state；
- command、return status、skip / xfail / deselection policy；
- artifact source identity 和 reviewer verdict。

`artifacts/quality/latest.md` 必須逐欄檢查 identity。若仍指向
`ux/assistant-product-v1@3869aaef`、dirty tree 或不同 commit，它只能算 baseline /
checkpoint evidence。

## Handoff Exit Condition

必須同時成立：

1. Audit 中沒有 code-controllable P0/P1 open item。
2. Focused regression、same-class/source guards、real happy path、deterministic oracle 和 strict
   multi-dataset gate 均由 final commit 重跑。
3. 固定 15-dataset ready plan 與 source/BIDS checksums 通過；30 個 cold/replay GUI receipts
   全綠，且任一 cancellation 都在同一 journey 重試成功。
4. Granite/RAG 和 UI artifacts 是 exact-source output；15-dataset Evaluation、Saliency Map、
   Spectrogram 與必要畫面由主 agent 逐張檢視。
5. Ruff、完整 configured product-source Basedpyright、architecture checks、relevant pytest、`mkdocs build --strict` 和
   handoff dashboard 全部來自同一 commit。
6. Branch 已 push；worktree clean，或只保留規則允許且未 stage 的 protected local settings。
7. Final report 明確列出 Windows DPI/multi-monitor、interactive 3D、teacher datasets 和
   long-session 等剩餘人工風險。

本候選另需讓新的 Linux parallel shards、focused Windows/macOS platform gate 與 coverage
aggregation 在同一 exact head 的 GitHub Actions 完成；本機 runner tests 不能替代該結果。

達成以上條件後，狀態才能提升為下一個 **Windows handoff candidate**。目前 `main` 只是已接受
的開發 checkpoint，仍不是 product complete。

## 本輪不做

- 不把 baseline branch fast-forward 或重新命名成 current candidate。
- 不新增 facade、silent compatibility fallback 或第二套 workflow truth。
- 不做 MCP hardening、MCP client certification 或 MCP thesis evidence；除非使用者明確要求。
- 不在產品 closure 完成前 freeze thesis benchmark 或宣稱 raw-model accuracy。
- 不把 automated dashboard、offscreen screenshots 或 launcher smoke 當成人工 acceptance。
- 不實作 Training timed hyperparameter search；本輪只交付可保留使用者逐欄位編輯的 deterministic recommended defaults。
- 不新增 planning 文件；新 current truth 回寫既有 canonical pages。
