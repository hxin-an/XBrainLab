---
name: release-packaging-reviewer
description: Use when reviewing XBrainLab desktop launchers, Windows/macOS/Linux packaging, first-run behavior, model cache setup, logs, CI matrix, code signing/notarization boundaries, and human click-through release evidence.
---

# release-packaging-reviewer

## 用途

用於檢查 XBrainLab 是否能被使用者真正啟動、安裝、診斷、交付，不只是從 repo 跑測試。

## 設計來源

已消化參考：

- PyInstaller：不是 cross-compiler；要做 Windows app 在 Windows build，Linux app 在 Linux build，
  macOS app 在 macOS build。
- Qt for Python deployment：deployment tool / spec 需要明確 entry point、virtualenv、platform。
- GitHub hosted runners：Windows、Ubuntu、macOS Intel / arm64 runner 有不同資源和限制。
- Apple notarization：macOS 外部發行通常需要 Developer ID signing + notarization 才能符合
  Gatekeeper 預期。

## 先讀

1. `docs/current.md`
2. `docs/operations.md`
3. `docs/planning/roadmap.md`
4. launcher / packaging scripts touched by the change
5. latest launcher / UI artifacts

## Review Gate

檢查：

- Windows Desktop launcher 是否指向 active repo / packaged app，而不是舊路徑。
- app 首次啟動、loading、main window geometry、多螢幕、log visibility 是否可驗收。
- local model first-run consent / disk / VRAM / cache 狀態是否清楚。
- stdout/stderr / log file 是否讓使用者有第二條診斷路徑。
- packaging 是否明確 target OS；不要用 Linux build 宣稱 Windows/macOS 可用。
- CI matrix 是否區分 Linux backend、Windows launcher/UI smoke、macOS compatibility smoke。
- macOS claim 是否有 macOS runner 或真 Mac evidence；Apple Silicon / MPS 不可由 Linux 推論。
- release artifact 是否包含版本、依賴、模型 policy、已知限制、重跑驗證。

## 打回條件

- 沒有真人或 automated click-through，就宣稱 desktop release ready。
- launcher 打開黑窗無 log 或卡住無可診斷訊息。
- 用 headless startup smoke 取代 Windows desktop interaction。
- macOS / Apple claim 只靠 Linux test。
- packaging 腳本寫死使用者本機路徑或舊 repo。

## 輸出格式

```md
## Release Verdict

- verdict: release-ready / smoke-only / not releasable

## Platform Evidence

## Launcher / Logs

## Packaging Risks

## Required Human Checks
```
