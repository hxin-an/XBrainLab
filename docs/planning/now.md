# XBrainLab Now

最後更新：`2026-08-15`

## 目前焦點

**保留 `v0.6.0` 作為唯一 Desktop GUI/source baseline，建立可阻擋明顯跑版的 UI visual-regression
guard；完成後才進入 Assistant task branch。**

本輪從 `main@665ce8e5` 建立 `test/ui-visual-regression-v1`。使用者要求 default-scale UI 變更必須
和 approved references 比對；layout、theme、font 或 dialog 變更另需 Windows 100/125/150% evidence。
本輪只修改 validation scripts、tests、CI 與 canonical docs，不修改產品 runtime、既有 UI layout 或
approved screenshot 內容，也不自動接受 visual drift。Repo-root `settings.json` 保留且不納入 commit。

## 後續順序

1. UI default-scale guard：capture exact-source candidate，對 `tests/baselines/ui/` 做 fail-closed 比對。
2. Windows DPI guard：layout/theme/font/dialog 變更時跑 100/125/150% capture 與 geometry contract。
3. Assistant：從完成上述 checkpoint 的最新 `main` 建短 branch。

## Assistant boundary

- 只走既有`ApplicationService / Command API`，不建立第二套state或capability policy。
- 先量測real Granite的tool selection、confirmation、retry/cancel與長session，再決定最小修復。
- MCP維持明確opt-in compatibility，不成為Assistant或thesis前置。
- 每個Assistant slice從tagged main另開短branch，完成focused evidence與使用者手測後才merge。

## Non-goals

- 不在GUI release branch加入新的Assistant功能。
- 不修改 `v0.6.0` tag/release、產品runtime行為、UI layout、models、training outputs或repo-root
  `settings.json`。
- 不從 retired worktrees 搬回 validation control plane、teacher campaign 或未提交中間版本。
- 不讓 offscreen capture 冒充 Windows native acceptance，也不因 CI 自動改寫 approved references。
- 不宣稱signed installer、scientific model quality、任意dataset support或product 1.0。
- 不恢復historical dashboard、tracked screenshots、舊Agent benchmark或第二份planning queue。

## Exit condition

UI regression slice只在下列條件全部成立後完成：

1. Default-scale candidate與approved reference使用同一 canonical path contract，缺圖、stale source或
   超出容許值的 drift都fail closed。
2. Default-scale gate覆蓋主視窗與五個panel；Windows 100/125/150% gate覆蓋靜態app-polish
   dialog/panel contract。Linux offscreen只作checkpoint，不冒充native Windows evidence。
3. Same-class source guard、focused/adjacent tests、static checks與strict docs build成功；主agent實際
   查看生成 artifact。
4. PR exact-head所有non-skipped CI成功並合入`main`。本輪不改產品行為，因此不要求額外產品手測。

驗證規則只讀[Validation](../validation/README.md)；長期目標讀[Roadmap](roadmap.md)。
