# XBrainLab Now

最後更新：`2026-08-24`

## 目前焦點

完成 `v0.8.0` release metadata 與 exact-commit 發布。產品 PR #48 已在使用者明確確認
`24f13b02bc6ac54c1610d1103a3c4530c047b764` 後合併；目前產品基線 merge commit 為
`5e5073e0d7a34927f18a40aff6e49d475e17467e`。

本 slice 只同步版本與 release truth，不再修改已驗收的產品行為。發布完成後沒有預設 active
implementation slice；下一個產品施工方向回到使用者討論與排序。

## Outcome 與 evidence

- `pyproject.toml`、package fallback 與 `AppConfig.VERSION` 一致為 `0.8.0`。
- CHANGELOG、README 與 current truth 以 **XBrainLab 0.8.0 — Saliency Refresh** 描述同一個
  source release boundary。
- Release metadata PR 必須由最新 `main` 建立，所有 non-skipped checks 對 exact head
  `completed/success` 後才可 merge。
- Annotated tag `v0.8.0` 與 GitHub Release 只能指向 release metadata PR 的 exact main merge commit。

## Scope、non-goals 與 UI 確認

- Scope：四處既有版本 contract、CHANGELOG、README、current truth、直接版本測試與 active plan cleanup。
- Non-goals：不改 UI、workflow、Assistant、資料、模型、訓練、evaluation、Saliency 計算或 packaging；不建立
  installer、compatibility path、owner、state machine 或第二套 release truth。
- Product UI／workflow 的 exact-head manual acceptance 已於 2026-08-24 取得並記錄在 PR #48；本 metadata-only
  slice 沒有新的使用者可見互動，因此不需要第二次 UI 手測。
- Release 只宣稱經驗收與 CI 保護的 source/desktop workflow refresh；不宣稱 signed installer、科學有效性、
  任意資料集／模型支援、安全零容忍或產品 1.0。

## 施工與 focused validation

1. 同步版本 contract，新增 `0.8.0` changelog，校準 README 與 `docs/current.md`。
2. 執行版本 contract test、`poetry check`、changed-source Ruff／format、MkDocs strict build 與 diff check。
3. 建立 metadata-only PR，確認 exact head/base 與所有 non-skipped CI completed/success。
4. Merge 後建立 annotated `v0.8.0` tag 與同名 GitHub Release，再核對 `main`、peeled tag 與 Release target。

## Stop conditions

- 任一版本來源、release title、tag 或 current truth 不一致；
- release diff 含產品行為、UI 或 dependency 變更；
- PR SHA／base 漂移，或 CI missing、pending、cancelled、failed；
- tag 已存在、tag target 不是 exact release merge commit，或 GitHub Release target 不一致。

任一條件成立即停止，不 merge、不 tag、不發布。
