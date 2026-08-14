# XBrainLab Now

最後更新：`2026-08-14`

這頁只保存目前主要目標、施工邊界與 exit condition。產品事實看
[Current](../current.md)，長期順序看 [Roadmap](roadmap.md)，驗證契約看
[Validation](../validation/README.md)。

## 目前焦點

**把所有本機 EEG datasets 收斂到 `XBRAINLAB_DATA_DIR/datasets/`，先 copy、checksum verify、
保留 rollback，再獨立決定 cleanup。**

Working desktop foundation 已經由 PR `#16` 合回 `main`；舊 reliability checkpoint 繼續留在 remote
作 provenance。Repo-root `settings.json` 是使用者本機設定，永遠不 stage、commit、revert 或覆寫。

## Active Delivery Context

| 項目 | Current value |
| --- | --- |
| Product baseline | 最新 `main`；實際 merge-base / SHA 由 Git 取得。 |
| Candidate | Dataset consolidation branch；實際 branch / pushed SHA 由 Git 與 PR 取得。 |
| Primary goal | 單一 storage layout、relocation-aware inventory、verified copy 與 UI/import tooling 對齊。 |
| Non-goals | 不在本 branch 修 P300 Saliency、不改 label semantics、不重跑 15-dataset GUI campaign、不刪舊 source/quarantine/worktree、不搬 model/RAG/output/log。 |
| Current classification | Short-branch implementation checkpoint；dry-run inventory 已辨識 15 formal BIDS、pinned public fixtures 與 legacy compact cache，尚未 merge 或執行 destructive cleanup。 |

## 本 branch 的產品邊界

- `XBRAINLAB_DATA_DIR` 仍是 durable application-data root；EEG payload 一律在其 `datasets/` child，
  不新增第二個 settings truth。
- Dataset import dialog 只使用 canonical dataset root 作起始位置，不限制使用者可匯入的外部路徑。
- Public fixture downloader 在明確設定 data root 時寫入 central `public-fixtures/`；CI 未設定時維持
  repo-local fallback。
- Migration command 預設只輸出 plan；copy 使用 dataset-relative checksum，staging 驗證成功後才
  atomic publish，且永遠不刪來源。

## 施工與 exit signal

| 順序 | 工作 | Exit signal |
| --- | --- | --- |
| 1 | Storage contract | `dataset_storage_layout()` 與 public fixture resolver 對同一 hierarchy；CI fallback 維持 hermetic。 |
| 2 | Inventory / copy | Dry-run manifest 列出 authority、bytes、checksum、source/target、rollback；代表 formal BIDS 與 pinned public profile copy+verify。 |
| 3 | Focused validation | Platform paths、migration、fixture downloader、Import picker與相鄰 workflow tests通過；Ruff/type/docs clean。 |
| 4 | PR integration | Focused commit push；PR base `main`；exact-head CI 所有 non-skipped checks completed/success；明確 merge回 `main`。 |
| 5 | Cleanup acceptance | 另行 Windows MI/P300 手測後，取得使用者明確授權才刪 orphan、quarantine、seed 與舊 copy。 |

第 4 項完成只代表 storage tooling 進入 `main`；第 5 項仍是獨立 destructive checkpoint。

## 合併後順序

1. **P300 Saliency fix**：從更新後的 `main` 另開短 branch，以真實
   `PostTrainingSaliencyStatus`、held-out class coverage、checkpoint 與 Captum/model evidence定責；
   不在 dataset branch 中猜修。
2. **後續產品工作**：效能、Assistant 與更多資料集 acceptance 各自使用單一主要目標的短 branch。

## Claim boundary

- 使用者回報 PhysionetMI 手動流程可完成，是重要人工 checkpoint，但不是 exact-head automated
  receipt，也不能外推成所有 BIDS / MI acceptance。
- P300 已能 import / train 的紀錄不等於 Saliency 成功；目前仍是下一 branch 的 open product bug。
- Offscreen Qt、Linux command-spine與 source guards 不取代 Windows native DPI、interactive 3D、
  long-session 或真人 usability acceptance。
- Dataset cleanup 在 PR merge、copy verification 與使用者確認前不執行；本 branch 不會讓目前資料或可運作程式消失。

## 本輪不做

- 不重新引入舊 reliability campaign。
- 不刪除 datasets、outputs、logs、worktrees；copy 階段保留全部 source。
- 不新增 facade、silent fallback、第二套 capability / state / status truth。
- 不用單一 PASS、聊天回報或舊 receipt 宣稱 handoff closure。
