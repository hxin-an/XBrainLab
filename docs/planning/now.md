# XBrainLab Now

最後更新：`2026-08-15`

## 目前焦點

**保留 `v0.6.0` 作為唯一 Desktop GUI/source baseline，先完成本機 dataset/worktree consolidation，
再建立 UI visual-regression guard，之後才進入 Assistant task branch。**

本輪 storage slice 不修改產品行為。它把已驗證 BIDS、public fixtures、唯一 raw source 與 manifests
集中到 durable data root，移除使用者已明確批准丟棄的舊 worktrees、branches、quarantine、seeds、
duplicate datasets 與 stale build outputs。下一個獨立 slice 才處理 UI baseline/DPI evidence。

## 後續順序

1. Storage consolidation：central authority、cleanup receipt、worktree/branch retirement。
2. UI regression guard：default-scale visual baseline；layout/theme/font/dialog 變更另跑 Windows
   100/125/150% evidence。
3. Assistant：從完成上述兩個 checkpoint 的最新 `main` 建短 branch。

## Assistant boundary

- 只走既有`ApplicationService / Command API`，不建立第二套state或capability policy。
- 先量測real Granite的tool selection、confirmation、retry/cancel與長session，再決定最小修復。
- MCP維持明確opt-in compatibility，不成為Assistant或thesis前置。
- 每個Assistant slice從tagged main另開短branch，完成focused evidence與使用者手測後才merge。

## Non-goals

- 不在GUI release branch加入新的Assistant功能。
- 不修改 `v0.6.0` tag/release、產品runtime行為、models、training outputs或repo-root `settings.json`。
- 不從 retired worktrees 搬回 validation control plane、teacher campaign 或未提交中間版本。
- 不宣稱signed installer、scientific model quality、任意dataset support或product 1.0。
- 不恢復historical dashboard、tracked screenshots、舊Agent benchmark或第二份planning queue。

## Exit condition

Desktop baseline只有在下列條件全部成立後才算完成：

1. Current tree只保留canonical docs與policy artifacts。
2. Product source與使用者手測版本一致，PR記錄manual acceptance。
3. Final PR exact-head所有non-skipped CI成功並合入`main`。
4. 實際main integration SHA的CI成功。
5. Annotated `v0.6.0` tag與Latest GitHub Release指向該main SHA。

驗證規則只讀[Validation](../validation/README.md)；長期目標讀[Roadmap](roadmap.md)。
