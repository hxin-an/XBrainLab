# XBrainLab Now

最後更新：`2026-08-15`

## 目前焦點

**保留 `v0.6.0` 作為唯一 Desktop GUI/source baseline，完成本機dataset/worktree cleanup的PR與CI，
再建立UI visual-regression guard，之後才進入Assistant task branch。**

本輪storage slice不修改產品行為。中央root已驗證BIDS、public fixtures、唯一raw source、legacy
compact source與manifests；舊worktrees/branches、quarantine、seeds、duplicate datasets與stale
build outputs已依使用者授權永久移除。`build/`目前不再承擔durable storage，下一個獨立slice才處理
UI baseline/DPI evidence。

## 後續順序

1. Storage consolidation：完成focused commit、PR、exact-head CI與merge。
2. UI regression guard：default-scale visual baseline；layout/theme/font/dialog變更另跑Windows
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

Storage slice只在下列條件全部成立後完成：

1. Central datasets、完整cleanup receipt與legacy copy receipt由同一final committed tool重新驗證；
   copy-only receipt不得冒充完整cleanup。
2. `build/` durable-storage audit無findings，retired worktree/branch不存在。
3. Focused tests、static checks與docs build成功。
4. PR exact-head所有non-skipped CI成功並合入`main`。

驗證規則只讀[Validation](../validation/README.md)；長期目標讀[Roadmap](roadmap.md)。
