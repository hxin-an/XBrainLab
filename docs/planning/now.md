# XBrainLab Now

最後更新：`2026-08-15`

## 目前焦點

**以 `v0.6.0` 凍結 Desktop GUI/source baseline，接著從 tagged `main` 建立新的 Assistant task
branch。**

Desktop baseline的release closure只包含：清除誤導文件/artifacts、統一version metadata、完成
exact-head validation、經PR合回`main`並建立tag/GitHub Release。Release closure期間不再修改已由
使用者手測通過的產品行為；若product source改動，必須重新手測並取得merge同意。

## 下一階段：Assistant

- 只走既有`ApplicationService / Command API`，不建立第二套state或capability policy。
- 先量測real Granite的tool selection、confirmation、retry/cancel與長session，再決定最小修復。
- MCP維持明確opt-in compatibility，不成為Assistant或thesis前置。
- 每個Assistant slice從tagged main另開短branch，完成focused evidence與使用者手測後才merge。

## Non-goals

- 不在GUI release branch加入新的Assistant功能。
- 不刪dataset、MOABB source/seeds、models、RAG、training outputs或registered worktrees。
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
