---
name: docs-site-product-designer
description: Use when redesigning or reviewing the XBrainLab MkDocs documentation site as a readable product portal, including information architecture, MkDocs Material cards/grids, artifact galleries, visual hierarchy, and screenshot-based design review.
---

# docs-site-product-designer

## 用途

用於把 XBrainLab documentation site 做成可讀、可信、可交接的 project portal。

這不是泛用 frontend skill。XBrainLab docs site 是工程文件站與產品狀態入口，不是 marketing
landing page，也不是炫技網頁。

## 設計來源

已消化參考：

- Anthropic frontend-design skill：UI 不能憑空套 generic AI pattern；要先決定清楚的設計方向，
  並用 typography、spacing、color、composition 做出一致品質。
- Material for MkDocs grids / cards：MkDocs Material 可以用 `attr_list`、`md_in_html`、
  `grid cards`、admonitions、tabs 和少量 HTML block 做出可維護的 index / overview pages。
- OpenAI skill-creator 原則：skill 要短、清楚、progressive disclosure；不要把所有規格塞進
  skill body。
- XBrainLab 使用者審核經驗：只要 agent 憑感覺做 UI，結果常常能 build 但不好看。docs site
  redesign 必須有 reference、layout spec、screenshot review 和打回條件。

## 先讀

1. `docs/index.md`
2. `docs/current.md`
3. `docs/planning/roadmap.md`
4. `docs/planning/now.md`
5. `docs/validation/README.md`
6. `mkdocs.yml`
7. `artifacts/ui/human-like-walkthrough/human-like-walkthrough.md`
8. `.agents/skills/docs-curator/SKILL.md`
9. `.agents/skills/ui-product-reviewer/SKILL.md`

## 核心原則

- Markdown 仍是 canonical content；HTML / CSS 只作 presentation layer。
- `site/` 是 MkDocs build output，不手改、不提交、不當 source。
- 首頁要像 project control room：一眼知道目前狀態、主要缺口、下一步、evidence 在哪。
- 使用者不應被 records / worklog / artifact raw list 淹沒。
- 不新增 `docs/site/` 或新的 truth layer，除非使用者明確要求。
- 不把所有 `.md` 轉成 `.html`。
- 不做大 hero、不做漸層炫技、不做裝飾性卡片牆。
- 不使用只有 marketing 感、沒有工程資訊密度的版面。
- 視覺方向應是 quiet engineering dashboard：清楚、克制、可掃讀、有層級。

## 推薦資訊架構

首頁第一屏應回答：

1. XBrainLab 現在是什麼階段。
2. 目前不能宣稱什麼。
3. 下一輪最重要的工作是什麼。
4. 最重要 evidence 在哪裡。

推薦 section：

- Current Status
- Product Readiness
- Architecture Health
- Data Interpretation
- Agent Tool-call Evidence
- UI Walkthrough Gallery
- Open Blockers
- Next Goal

## MkDocs Material 做法

優先使用：

- `admonition`
- `pymdownx.details`
- `pymdownx.superfences`
- `attr_list`
- `md_in_html`
- `grid cards`
- compact tables
- screenshots with short captions
- restrained custom CSS in `docs/stylesheets/extra.css`

若使用 grids / cards，先確認 `mkdocs.yml` 有：

```yaml
markdown_extensions:
  - attr_list
  - md_in_html
```

不要用不可維護的大段 inline style。少量 HTML block 可以接受，但內容仍應讓 agent 易讀易改。

## 設計流程

1. 先做 site brief，不直接改 UI。
2. 明確列出 target audience：使用者、開發者、未來 agent、論文/驗證讀者。
3. 明確列出第一屏 layout、navigation path 和每個 card 的資訊目的。
4. 實作前先指出哪些文件是 source truth，哪些只是 presentation。
5. 實作後跑 `poetry run mkdocs build --strict`。
6. 產出或檢查 built site screenshot；不能只說 build pass。
7. 用 `ui-product-reviewer` 做視覺/可讀性審核。
8. 如果 screenshot 第一眼仍像文件 dump，打回重做。

## Artifact 治理

`artifacts/` 是機器產物，不是文件 truth。

site 應只展示高價值 artifact 入口：

- quality dashboard
- human-like UI walkthrough
- tool-call eval dashboard
- MCP walkthrough
- Data Interpretation format matrix
- launcher / packaging evidence

需要新增時，優先新增 `artifacts/README.md` 或 validation artifact index，而不是把所有 artifact
都塞進首頁。

## 打回條件

- 首頁像文件列表，而不是狀態入口。
- 第一屏看不出 current status / blocker / next work。
- 使用大量裝飾但沒有資訊密度。
- 卡片太多、層級太亂、文字太長。
- 把 `records/worklog.md` 這類流水帳當主要入口。
- 手改 `site/` build output。
- 只跑 `mkdocs build`，沒有 screenshot / visual review。
- 新增不存在的 status 或誇大 claim。

## 輸出格式

```md
## Docs Site Design Verdict

- verdict: ready to implement / needs brief / reject

## Proposed Information Architecture

## Visual Direction

## Files To Change

## Build And Screenshot Gates

## Claim Boundaries
```
