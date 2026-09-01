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
`v0.8.0` 是 Saliency Refresh source baseline：保留 `v0.7.0` 的 bounded local Assistant 與相同
GUI／Command owners，並整理 exact Fold／Fold Set 計算生命週期、class 檢視、2D／3D presentation 與
import review recovery。歷史 MCP executable surface 已退役。

## 啟動

Linux／macOS 開發環境使用 Poetry 管理：

```bash
poetry sync
poetry run python run.py
```

Windows 不使用上面的無 extra 同步；若要以 NVIDIA CUDA 執行本機 Assistant，首次改用：

```powershell
poetry config virtualenvs.in-project true --local
poetry config installer.re-resolve true --local
$python = py -3.12 -c "import sys; print(sys.executable)"
poetry env use $python
poetry sync --with llm -E cuda
poetry run python run.py --model local
```

日後同步 CUDA 開發環境仍使用 `poetry sync --with llm -E cuda`；Windows CPU 環境則明確使用
`poetry sync -E cpu` 取得官方 `+cpu` wheels。Windows 不支援省略或同時選取這兩個 extra。
詳見[本機開發環境](docs/developer/local-setup.md)。

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

`v0.8.0` 代表經真人 workflow 手測與同一 Command spine 保護的 Desktop GUI／Local Assistant／
Saliency Refresh source baseline。它不代表 signed installer、安全零容忍、任意 EEG dataset 或模型全面
支援、scientific attribution／model-quality certification 或整體產品 1.0。
