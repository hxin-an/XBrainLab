# Documentation Site Redesign Workflow

用於重設 XBrainLab MkDocs documentation site，讓它成為可讀的 project portal。

這個 workflow 不把 Markdown 轉成 HTML，也不手改 `site/`。`site/` 是 build output。

## 使用 skills

- `.agents/skills/docs-site-product-designer/SKILL.md`
- `.agents/skills/docs-curator/SKILL.md`
- `.agents/skills/ui-product-reviewer/SKILL.md`
- `.agents/skills/validation-runner/SKILL.md`

## 1. 先做 Brief

先讀：

1. `mkdocs.yml`
2. `docs/index.md`
3. `docs/current.md`
4. `docs/planning/roadmap.md`
5. `docs/planning/now.md`
6. `docs/validation/README.md`
7. `artifacts/ui/human-like-walkthrough/human-like-walkthrough.md`
8. `artifacts/agent_evals/dashboard.md`

輸出 brief，至少包含：

- site 的主要讀者
- 首頁第一屏要回答的問題
- navigation hierarchy
- artifact 應如何展示
- 哪些內容不該放在首頁
- 需要改哪些檔案

不要在 brief 前直接大改。

## 2. 實作範圍

允許優先改：

- `docs/index.md`
- `docs/current.md`
- `docs/planning/roadmap.md`
- `docs/validation/README.md`
- `docs/architecture/README.md`
- `docs/stylesheets/extra.css`
- `mkdocs.yml`
- `artifacts/README.md`

避免：

- 新增大量一級 docs 文件。
- 新增 `docs/site/`。
- 手改 `site/`。
- 把 records / worklog 提升成主要導航。
- 把 build artifact 當 current truth。

## 3. 視覺方向

目標是 quiet engineering dashboard：

- 克制、清楚、資訊密度合理。
- 以 status cards、evidence matrix、short captions、screenshot gallery 建立層級。
- 不做大 hero。
- 不做裝飾性漸層。
- 不做 marketing landing page。
- 不使用不存在的產品 claim 填充畫面。

## 4. 驗證

至少跑：

```bash
poetry run mkdocs build --strict
```

若有修改 CSS / 首頁 layout，還要產出 screenshot 或用瀏覽器檢查 built site。

檢查：

- 首頁第一屏是否能看懂目前狀態。
- navigation 是否少而清楚。
- cards / tables / screenshots 是否沒有擠壓、溢出、過度裝飾。
- `site/` 沒被提交。
- claim boundary 沒被誇大。

## 5. 完成輸出

完成時回報：

- 改了哪些 source 文件。
- `site/` 是否只是 build output。
- `mkdocs build --strict` 結果。
- screenshot / visual review 結果。
- 仍然不好看的地方或需要使用者審美決策的地方。
