# XBrainLab 操作筆記

最後更新：`2026-05-09`

## 工作路徑

```bash
cd /mnt/d/workspace_v2/projects/lab/XBrainLab
```

不要把新工作寫回舊路徑 `/mnt/d/repos/XBrainLab`；它目前只作 archive / reference。

## 環境狀態

標準 dev/test/docs env 已可用。Poetry virtualenv：

```text
/home/administrator/.cache/pypoetry/virtualenvs/xbrainlab-TKrzxeIe-py3.12
```

已完成：

- `poetry install --with dev,test,docs`
- import probe：`PIL`、`mne`、`PyQt6`、`torch`、`pytest`、`XBrainLab`
- docs build：`poetry run mkdocs build --strict`
- local assistant runtime：primary / fallback cache、GPU prompt smoke、structured-output smoke

local assistant runtime 已完成 primary / fallback smoke 驗證。`accelerate` 和
`bitsandbytes` 不是預設硬需求；4-bit loading 仍是 optional path。

## 桌面啟動

可點擊 launcher 已放在 Windows Desktop：

```text
/mnt/c/Users/Administrator/Desktop/XBrainLab.cmd
```

repo 內保留 launcher source：

```text
scripts/launchers/xbrainlab_wsl_launcher.cmd
scripts/launchers/xbrainlab_wsl_launcher.ps1
```

launcher 會：

- 進入 `/mnt/d/workspace_v2/projects/lab/XBrainLab`。
- 優先使用 WSL 內的 `poetry run python run.py`。
- 找不到 `poetry` 時嘗試 `/home/administrator/.local/bin/poetry`，再退到 `python run.py`。
- 將 log 寫到 Windows：

```text
%LOCALAPPDATA%\XBrainLab\logs\launcher-*.log
```

啟動 smoke：

```bash
timeout 35s xvfb-run -a poetry run python run.py --model local
```

`MainWindow initialized` 出現後因測試 timeout 結束屬於預期，代表 startup 未在初始化階段崩潰。

Windows launcher command walkthrough：

```bash
poetry run python scripts/dev/capture_windows_launcher_walkthrough.py --output-dir artifacts/launcher
```

這會從 Windows `cmd.exe` / PowerShell / `wsl.exe` 驗證 Desktop command、launcher log mirror
和 bounded startup path，artifact 寫到 `artifacts/launcher/windows-launcher-walkthrough.*`。
它不是真人桌面 click-through。

## Local LLM Runtime

目前 product catalog 只允許非中國來源模型：

| role | model | estimated download | VRAM estimate | cache |
| --- | --- | ---: | ---: | --- |
| primary | `microsoft/Phi-4-mini-instruct` | 7.69 GB | 9.0 GB | downloaded |
| fallback | `microsoft/Phi-3.5-mini-instruct` | 7.64 GB | 8.5 GB | downloaded |

目前 cache：

```text
XBrainLab/llm/core/models
```

目前用量約 `15.34 GB`，低於 20GB 上限。已刪除舊 Qwen cache；不要重新下載或使用
Qwen、DeepSeek、Yi、GLM、Baichuan、InternLM、MiniCPM 等中國公司或中國來源模型。

下載前檢查：

```bash
poetry run python scripts/dev/plan_local_model_download.py --format markdown
poetry run python scripts/dev/plan_local_model_download.py \
  --model microsoft/Phi-3.5-mini-instruct --format markdown
```

已下載的模型會被視為 cached：preflight 應顯示 `ok=True`、estimated download `0.00 GB`，
projected cache 不會重複加上同一模型大小。

runtime health check：

```bash
poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown
poetry run python scripts/dev/inspect_local_assistant_runtime.py \
  --format markdown --prompt-smoke --structured-smoke
poetry run python scripts/dev/inspect_local_assistant_runtime.py \
  --model microsoft/Phi-3.5-mini-instruct \
  --format markdown --prompt-smoke --structured-smoke
```

清理模型 cache 時，只刪明確模型目錄與 lock，例如：

```bash
rm -rf \
  XBrainLab/llm/core/models/models--microsoft--Phi-4-mini-instruct \
  XBrainLab/llm/core/models/.locks/models--microsoft--Phi-4-mini-instruct
```

清理後重新跑 preflight，確認 projected cache 仍低於上限。

## 常用指令

安裝標準依賴：

```bash
poetry install --with dev,test,docs
```

啟動 app：

```bash
poetry run python run.py
```

建立文件站：

```bash
poetry run mkdocs build --strict
```

部署文件站：

- GitHub Pages workflow：`.github/workflows/docs-pages.yml`
- 觸發方式：push 到 `main`，或 GitHub Actions 內手動 `workflow_dispatch`
- publish source：GitHub Pages artifact，內容來自 build output `site/`

`site/` 仍是 build output，不手改、不 commit。GitHub repo settings 需要將 Pages source 設成
`GitHub Actions`，部署後網址由 workflow 的 `github-pages` environment 顯示。

刷新 fast quality dashboard：

```bash
poetry run python scripts/dev/update_quality_dashboard.py
```

跑 UI 測試 wrapper：

```bash
scripts/dev/run_ui_pytest.sh tests/unit/ui -q
```

跑 targeted pipeline smoke：

```bash
poetry run pytest --capture=sys \
  tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics \
  tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet \
  -q
```

查看目前 dashboard：

```bash
cat artifacts/quality/latest.md
```

## 操作限制

- 目前 legacy 閱讀面已清理完成；目前主線是 product-delivery engineering。
- 可以推進 backend、UI、agent、local LLM 和 desktop launcher，但要維持可驗證、可回滾理解的工程邊界。
- 不要把 `/mnt/d/repos/XBrainLab` 當 active repo。
- assistant product runtime 已 local-only；remote backend modules 已從 product package 移除，
  remote SDK 只留 optional `legacy-remote-llm` dependency group。
- local LLM smoke 目前另行驗證，尚未納入 fast dashboard 預設 profile；產品驗收時要單獨跑 local health / prompt / structured smoke。
- 真 local LLM 長時間 ChatPanel walkthrough 尚未跑；不要把 standalone local runtime smoke
  說成完整 assistant product acceptance。
- 多 worker 同時工作時，只改自己負責的檔案，不 revert 既有變更。
