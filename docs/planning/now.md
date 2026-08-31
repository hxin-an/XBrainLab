# XBrainLab Now

最後更新：`2026-08-31`

## Current baseline

PR #89 的 3D Epoch time control 與 PR #90 的 Recipe Save／Reload lifecycle 已由使用者對各自
exact head 完成人工驗收並同意 merge。兩者合併後的 `main` 已通過 exact-source push CI：完整
Linux suite、Windows／macOS lifecycle、Windows 100／125／150% DPI、default visual regression、
human-like walkthrough 與 required public multi-dataset gate 均為 `completed/success`。

開始本 slice 前已清理所有舊 task worktree 與 `/tmp/xbrainlab*` 驗證殘留；唯一產品基線是同步
`origin/main` 的 `main`。Repo-root `settings.json` 的本機修改仍由使用者擁有。本輪不再增加功能，而是
將這個已驗證基線收斂成 `v0.9.0` Desktop Workflow Stabilization source release。

## Audit conclusion

Architecture、code、test/release、UI/data/performance 四個面向的唯讀審核沒有發現需要在 release 前
進行大型重構的 source blocker：

- UI、Assistant 與 scripts 仍共用 `ApplicationService / Command API`；沒有第二套產品 workflow state。
- Data Interpretation 維持 scan → review → validate → confirm → apply → optional recipe 的單一 owner chain。
- 大型 coordinator 與 compatibility helpers 是維護債，不是目前可重現的 release defect；release 前拆分
  反而會擴大 lifecycle regression 風險。
- Import 的代表性產品路徑沒有量到 UI freeze，但較重三-run BIDS profile 仍可能超過 10 秒；本 release
  不宣稱固定 latency SLA。

## Release claim

候選版本為 `v0.9.0`，定位為 **Desktop Workflow Stabilization source baseline**：

- reviewed EEG/BIDS import、label/event interpretation、recipe Save／Reload 與 Electrode Layout；
- preprocess、epoch、dataset split、class weighting、early stopping、training、evaluation 與 saliency；
- 3D epoch-relative time slider／numeric control；
- local Granite Assistant 透過既有 18-action command surface 操作相同 workflow。

下列內容明確不在 claim 內：

- Assistant Stable promotion：目前 bounded baseline 是 `22/24` product no-action、`6/7` clarification
  execution boundary，不是 `24/24`、`7/7`；
- signed Windows installer、一般使用者安裝／升級／移除流程；
- 大型 BIDS 固定 10 秒內、任意資料集／模型全面支援；
- portable Recipe：目前 JSON 依賴原始 source／label paths，資料搬移後需要未來獨立的 relocation flow；
- scientific model、training、saliency 或 attribution validity certification。

## Scope and non-goals

本 slice 只允許：

1. 將 package、runtime fallback 與 Commitizen version 單一同步為 `0.9.0`；
2. 更新 version contract test；
3. 將 README、CHANGELOG、`docs/current.md` 與本 plan 對齊同一 release claim；
4. 產生 exact-candidate validation、bounded Assistant report、PR 與 manual-acceptance record。

不修改任何 workflow logic、UI layout/copy、Assistant prompt/tool contract、data semantics、performance path、
owner、state machine、receipt 或 compatibility layer。Production 變更只限既有版本常數，owner delta `0`。

## Roles

- **Root coordinator**：維護本 plan、鎖 scope、核對 exact source／CI／artifacts、建立 PR，並在 manual
  acceptance 後執行 merge、tag 與 release identity verification。
- **Release implementer**：只改版本檔、version test 與四份 canonical release 文件；不碰產品行為。
- **Independent reviewer**：核對所有版本字串、release claim、歷史 tag、tests 與 diff scope；不在作者
  branch 補功能。

## Validation and stop condition

1. 版本一致性：`pyproject.toml` Poetry／Commitizen、`XBrainLab/config.py`、
   `XBrainLab/__init__.py`、version contract test 全部是 `0.9.0`，且舊 `v0.8.0` history 不被覆寫。
2. Focused gates：version test、Ruff、Basedpyright、architecture compliance、diff check、MkDocs strict 與
   canonical docs/source audit。
3. Exact candidate：PR head/upstream一致，所有 non-skipped GitHub checks `completed/success`；Assistant 保存
   同一 exact source 的完整 bounded report，不把 known limitation 灌成 Stable PASS。
4. Manual acceptance：使用者在 exact candidate 完成 source launch 與核心 workflow smoke，明確同意 merge。
   Source 再改即失效。
5. Merge 後重新核對 `main` merge commit；只有 user approval、version identity、CI 與 tag target 全部對應
   時才建立 annotated `v0.9.0` tag／GitHub source release。

若實作需要改產品邏輯、放寬 validation gate、隱藏 Assistant／performance limitation、建立 installer 或處理
Recipe relocation，立即停止並另開獨立 plan／PR；不得把它們塞入 release metadata diff。
