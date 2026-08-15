# XBrainLab Artifact Policy

最後更新：`2026-08-15`

`artifacts/` 只保留 policy 與 ignore 規則，不保存 current product evidence。

- 開發期、可重建的輸出寫到 ignored `build/dev-artifacts/<family>/`。
- Handoff evidence 寫到 ignored `build/handoff-evidence/<full-SHA>/`，並綁定完整 commit、source
  fingerprint、dirty state、generator、environment、claims、limitations 與檔案 hashes。
- 視覺 regression 的 approved reference 只放 `tests/baselines/ui/`。
- Canonical product truth 只在 `docs/current.md`；artifact 名稱中的 `latest`、`final`、`passed` 或
  `release-candidate` 不構成證據。
- 不同格式不等於不同資料集；自動 screenshot 不取代 Windows 真人驗收。

任何新 tracked evidence 都應由 source guard 拒絕。歷史 artifacts 可從 Git history 取得，不得複製回
current tree 作為 active dashboard 或 release claim。
