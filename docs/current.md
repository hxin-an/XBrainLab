# XBrainLab 目前狀態

最後更新：`2026-08-15`

## 一句話

XBrainLab `0.6.0` 是 Windows Desktop GUI/source baseline：使用者可由 Dataset import/review 經
Preprocess、Epoch、Split/Training、Evaluation 到 Saliency visualization。Assistant 尚未成為正式
產品能力，下一階段會從 tagged `main` 獨立推進。

## Current product truth

| 區域 | 目前能相信 | 邊界 |
| --- | --- | --- |
| Command spine | `ApplicationService / Command API` 是 GUI、Assistant 與 scripts 共用的產品命令入口。 | Lower-level domain tests 仍可直接使用 Study/managers；不得把它們接回產品 UI mutation。 |
| Data import | Formal BIDS subject selection、reviewed import、external/internal label mapping、recipe與多格式 loader存在。 | 不是 full BIDS validator，也不能外推到所有資料集與 proprietary formats。 |
| Preprocess / Epoch | Filtering、resample、rereference、normalize、channel selection與reviewed epoch flow存在，長工作有 owned lifecycle。 | Protocol choice與科學正確性仍由使用者負責。 |
| Split / Training | Split preview、training settings、fold/repeat plans與training history存在。每次 Start Training有獨立 round identity。 | Recommendation不是AutoML或最佳參數保證。 |
| Evaluation | Individual fold/run支援Train、Validation、Test；cross-fold Summary只pool同一training round的disjoint Test masks。 | `All Folds`的Split只有Test是刻意的統計邊界。 |
| Saliency | 明確Compute Saliency、累加method recompute、Map/Spectrogram/Topographic/3D publication存在。 | 不代表attribution具科學有效性，也不保證所有模型梯度相容。 |
| Assistant | Local Granite、tool admission、confirmation與structured result骨架存在。 | 尚未Assistant-ready；real-model準確率、長session與Windows驗收待下一階段。 |
| MCP | Code/tests可供明確opt-in compatibility。 | 不屬於active roadmap、release或thesis prerequisite。 |
| Packaging | Windows launcher與source啟動方式存在。 | 沒有signed installer。 |

## Evidence truth

- Current product baseline永遠是Git的`main`；branch、SHA與dirty state從Git取得，不寫死在文件。
- Generated evidence只寫入ignored `build/dev-artifacts/`或
  `build/handoff-evidence/<full-SHA>/`；這些是可丟棄的當次輸出，不是durable storage。
  `artifacts/`不保存current evidence。
- Offscreen Qt、dashboard與自動journey是工程證據，不取代Windows真人操作。
- Visible UI source變更會產生exact-source default-scale candidate，並和
  `tests/baselines/ui/` approved references做fail-closed比對。UI layout/theme/font/dialog路徑另由
  Windows Qt platform在100/125/150%跑app-polish geometry/pixel contract；它仍不取代真人Windows
  DPI、多螢幕或remote-desktop acceptance。
- 任何產品行為變更都必須由使用者手測通過並明確同意merge；product source變更後須重新批准。
- Repo-root `settings.json`是本機設定，不屬於release tree。

## Dataset storage boundary

`XBRAINLAB_DATA_DIR/datasets/`是唯一central local hierarchy，分為source、bids、public-fixtures、
manifests與quarantine。這台開發機目前使用
`/mnt/d/workspace_v2/.xbrainlab-data/datasets/`；其中保存15個formal BIDS、唯一MOABB raw source、
legacy compact source、pinned public fixtures與relocation-aware checksums/receipts。Import dialog只把
它當起始位置，仍可選外部路徑。Repo `build/`只允許可重建、可丟棄的當次artifact，不再保存dataset、
seed、cache authority或retired worktree。

## Release boundary

`v0.6.0`只宣稱經使用者手測與CI保護的Windows Desktop GUI/source baseline；不宣稱signed
installer、Assistant-ready、scientific quality、任意dataset全面支援或產品1.0。
