# XBrainLab Now

最後更新：`2026-08-14`

這頁只保存目前主要目標、施工邊界與 exit condition。產品事實看
[Current](../current.md)，長期順序看 [Roadmap](roadmap.md)，驗證契約看
[Validation](../validation/README.md)。

## 目前焦點

**把使用者已能操作的 desktop product foundation 從舊 reliability checkpoint 擷取成一條從最新
`main` 建立、可審查且可合併的 product-only PR。**

舊 checkpoint 保留在 remote 作 rollback provenance；不把 MOABB campaign、materializer、GUI
driver、delivery receipts、generated BIDS 或 build artifacts 合回 `main`。Repo-root
`settings.json` 是使用者本機設定，永遠不 stage、commit、revert 或覆寫。

## Active Delivery Context

| 項目 | Current value |
| --- | --- |
| Product baseline | 最新 `main`；實際 merge-base / SHA 由 Git 取得。 |
| Candidate | Product-foundation extraction branch；實際 branch / pushed SHA 由 Git 與 PR 取得。 |
| Primary goal | 保留完整 current `XBrainLab/**` runtime 與 matching product tests，排除 campaign-only code/dependencies，經 PR 合回 `main`。 |
| Non-goals | 不在本 branch 搬 datasets、不刪 76GB build corpus、不修 P300 Saliency、不增加 trial-label產品複雜度、不做 MOABB delivery automation。 |
| Current classification | Draft PR `#16` validated checkpoint；第一輪 exact-head CI 已揭露並定責三個 failing shards，本機修復已通過；新 exact-head CI 與 merge 尚未完成。 |

## 本 branch 的產品邊界

- `ApplicationService / Command API` 仍是 UI、Assistant 與 headless scripts 共用的 command spine。
- 保留 formal BIDS inventory / subject selection、reviewed import/apply、label lexeme identity、owned
  operation progress/cancel、detached preprocess/epoch preparation、Training preview、Evaluation 與
  explicit Saliency publication。
- 保留 product-facing Qt status/publication lifecycle，以及與上述 runtime 直接對應的 backend、UI、
  integration regression。
- RAG 保留 maintained LangChain partner packages；MOABB、BIDS validator、conversion/download tools
  不成為 product runtime direct dependencies。
- `scripts/dev/handoff_gate_spec.py` 與 evidence recorder 維持 `main` 的 canonical product registry，
  不攜帶舊 15-dataset campaign gate。

## 施工與 exit signal

| 順序 | 工作 | Exit signal |
| --- | --- | --- |
| 1 | Product extraction | `XBrainLab/**` 與 preserved checkpoint 的 final product tree parity；campaign denylist、build data、`settings.json` 都不在 diff。 |
| 2 | Dependency / docs sync | Product-only lock 可重建；canonical current/architecture/now 不宣稱 campaign 或未驗收資料集完成。 |
| 3 | Focused validation | Ruff、configured product Basedpyright、import/owned-work/preprocess/training/eval/saliency/UI adjacent suites通過；同類 source sweep clean。 |
| 4 | User-style evidence | 一條 canonical real-data command-spine path 與必要 UI artifact 可回指同一 candidate SHA；主 agent 親自檢查可見 artifact。 |
| 5 | PR integration | Focused commits push；PR base `main`；exact-head CI 所有 non-skipped checks completed/success；明確 merge commit 回 `main`。 |

只有第 5 項完成後，這個程式基礎才成為新的 `main`。在此前只能稱 validated checkpoint，不能稱
handoff-ready、release-ready 或 product complete。

## 合併後順序

1. **Dataset consolidation**：集中到 `tests/fixtures/data/`；保留 tracked fixtures 與 15 個 formal
   BIDS datasets，先做 checksum / manifest / product import 驗證，再刪 raw seeds、quarantine、舊
   worktree copies 與使用者已允許刪除的 unverified Zenodo fixture。Models、RAG cache、output 與 logs
   不混入 dataset root。
2. **P300 Saliency fix**：從更新後的 `main` 另開短 branch，以真實
   `PostTrainingSaliencyStatus`、held-out class coverage、checkpoint 與 Captum/model evidence定責；
   不在 foundation extraction 中猜修。
3. **後續產品工作**：效能、Assistant 與更多資料集 acceptance 各自使用單一主要目標的短 branch。

## Claim boundary

- 使用者回報 PhysionetMI 手動流程可完成，是重要人工 checkpoint，但不是 exact-head automated
  receipt，也不能外推成所有 BIDS / MI acceptance。
- P300 已能 import / train 的紀錄不等於 Saliency 成功；目前仍是下一 branch 的 open product bug。
- Offscreen Qt、Linux command-spine與 source guards 不取代 Windows native DPI、interactive 3D、
  long-session 或真人 usability acceptance。
- Dataset cleanup 在 PR merge 與使用者確認前不執行；本 branch 不會讓目前資料或可運作程式消失。

## 本輪不做

- 不合併、squash 或 cherry-pick 整條舊 reliability branch。
- 不把 campaign scripts/tests/docs/dependencies 改名後混入 product foundation。
- 不移動或刪除 datasets、outputs、logs、worktrees。
- 不新增 facade、silent fallback、第二套 capability / state / status truth。
- 不用單一 PASS、聊天回報或舊 receipt 宣稱 handoff closure。
