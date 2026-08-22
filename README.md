# XBrainLab

XBrainLab 是本地優先的 EEG/BCI 桌面分析工具。主要 workflow 是：

```text
Import and review EEG data
  -> Preprocess
  -> Create epochs
  -> Split and train
  -> Evaluate
  -> Visualize saliency
```

`ApplicationService / Command API` 是 GUI、Assistant 與開發 scripts 共用的產品命令邊界。
`v0.7.0` 加入 bounded local Assistant baseline：固定 Granite 模型使用strict structured envelope、
18個核准action與既有GUI／Command owners。歷史MCP executable surface已退役。

## 啟動

使用 Poetry 管理的環境：

```bash
poetry install
poetry run python run.py
```

目前發行物是 source/GUI baseline，不是 signed installer。Windows launcher 只適用於已配置的開發
機器，不能視為一般使用者安裝程式。

## 文件入口

- [新貢獻者指南](docs/developer/README.md)
- [目前產品真相](docs/current.md)
- [目前工作與下一階段](docs/planning/now.md)
- [目前架構](docs/architecture/README.md)
- [驗證與 evidence contract](docs/validation/README.md)
- [目標態](docs/target/README.md)
- [使用者操作指南](user_docs/index.md)
- [版本紀錄](CHANGELOG.md)

詳細歷史不再維護第二份流水帳；需要時由 Git history、合併 PR、tag 與 GitHub Release 追溯。

## 開發邊界

- `main` 是唯一產品基線，變更以短 branch + PR 整合。
- `settings.json` 是本機 runtime 設定，不得提交或覆寫。
- Dataset、model/RAG cache、training output 與 generated evidence 各有獨立 storage owner。
- 開發 artifact 寫到 ignored `build/dev-artifacts/`；exact handoff evidence 寫到
  `build/handoff-evidence/<full-SHA>/`。
- 任何改變產品行為的 PR，必須先由使用者手測通過並明確同意 merge；CI 和自動 screenshot 不能
  取代人工批准。

## 準確的 release claim

`v0.7.0` 代表經真人workflow手測與同一Command spine保護的Desktop GUI／Local Assistant source
baseline。它不代表 signed installer、安全零容忍、任意 EEG dataset 全面支援、scientific
model-quality certification 或整體產品 1.0。
