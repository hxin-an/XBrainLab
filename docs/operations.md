# XBrainLab 操作筆記

最後更新：`2026-08-11`

## 工作路徑

```bash
cd /mnt/d/workspace_v2/projects/lab/xbrainlab
```

不要把新工作寫回舊路徑 `/mnt/d/repos/XBrainLab`；它目前只作 archive / reference。

上面的 root checkout 是 launcher 的預設 canonical merge target，不代表每個驗證中的 worktree。
啟動或產生 handoff evidence 前，先用 `git rev-parse --show-toplevel`、
`git branch --show-current` 與 `git status --short` 確認實際 source identity。每項工作使用從最新
`main` 建立的短 task branch；尚未 merge 回 root checkout 前，不可把 Desktop launcher 的 root
startup 當成該 task candidate 的證據。

## 環境狀態

標準 dev/test/docs env 已可用。Poetry virtualenv：

```text
/home/administrator/.cache/pypoetry/virtualenvs/xbrainlab-TKrzxeIe-py3.12
```

已完成：

- `poetry install --with dev,test,docs`
- import probe：`PIL`、`mne`、`PyQt6`、`torch`、`pytest`、`XBrainLab`
- docs build：`poetry run -- mkdocs build --strict`
- local assistant runtime：catalog / download preflight / health-check scripts

目前 exact primary `ibm-granite/granite-3.3-2b-instruct` 已有本機 cache，GPU prompt
smoke、structured-output smoke 與受控產品 workflow 均已通過。`accelerate` 和
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

- 已安裝的 Desktop command 預設指向 root checkout
  `D:\workspace_v2\projects\lab\xbrainlab`；PowerShell launcher 再從自身位置解析 WSL 路徑。
  這不是任意 worktree 的自動追蹤機制。驗證尚未 merge 的 candidate 時，必須明確設定
  `XBRAINLAB_REPO_WIN` 或直接從該 worktree 執行，並在 artifact 中核對 branch、full SHA 與
  dirty state。
- 優先使用 WSL 內的 `poetry run -- python run.py`。
- 找不到 `poetry` 時嘗試 `/home/administrator/.local/bin/poetry`，再退到 `python run.py`。
- 在 repo 所在的 Windows 磁碟建立 rebuildable cache boundary。預設 cache root 是
  `<repo drive>:\XBrainLabCache`，可用 `XBRAINLAB_CACHE_ROOT_WIN` 覆寫。RAG cache 位於
  `<cache root>\rag`。若 canonical repo 內已有經驗證的 historical model cache，launcher
  會沿用 `XBrainLab\llm\core\models`，避免為同一個 Granite 模型重複下載；新安裝則使用
  `<cache root>\models`。這兩條路徑都在 repo 所在磁碟，不會把大型模型下載到 WSL root。
- 將 log 寫到 Windows：

```text
%LOCALAPPDATA%\XBrainLab\logs\launcher-*.log
```

啟動 smoke：

```bash
timeout 35s xvfb-run -a poetry run -- python run.py --model local
```

`MainWindow initialized` 出現後因測試 timeout 結束屬於預期，代表 startup 未在初始化階段崩潰。

Windows launcher command walkthrough：

```bash
poetry run -- python scripts/dev/capture_windows_launcher_walkthrough.py --output-dir artifacts/launcher
```

這會從 Windows `cmd.exe` / PowerShell / `wsl.exe` 驗證 Desktop command、launcher log mirror
和 bounded startup path，artifact 寫到 `artifacts/launcher/windows-launcher-walkthrough.*`。
它不是真人桌面 click-through。

`artifacts/launcher/windows-launcher-walkthrough.md` 是可重建的自動化證據；使用前必須核對
branch、full commit SHA 與 dirty state，不能把舊的 `passed` 當成目前 handoff 結果。
PowerShell launcher 會從自身位置解析 WSL 路徑；desktop command 允許用
`XBRAINLAB_REPO_WIN` 指向搬移後的 repo。

## Local LLM Runtime

目前 product catalog 只允許非中國來源模型：

| role | model | estimated download | VRAM estimate | cache |
| --- | --- | ---: | ---: | --- |
| primary | `ibm-granite/granite-3.3-2b-instruct` | 5.08 GB | 6.0 GB | cached |

`microsoft/Phi-4-mini-instruct` 與 `microsoft/Phi-3.5-mini-instruct` 是 retired model IDs：
不在 product catalog、不作 fallback，也不是目前 cache 的必要內容。

目前 cache：

```text
XBrainLab/llm/core/models
```

模型 cache 是 **checkout/path-scoped runtime state**，不是 repo-wide 常數。PowerShell launcher 會明確設定
`XBRAINLAB_MODEL_CACHE_DIR` 和 `XBRAINLAB_RAG_CACHE_DIR` 後才啟動產品。直接執行
`poetry run -- python run.py` 不會經過 launcher，因此若需要使用相同的 cached Granite，先在
該 shell 明確設定：

```bash
export XBRAINLAB_MODEL_CACHE_DIR="$PWD/XBrainLab/llm/core/models"
export XBRAINLAB_RAG_CACHE_DIR=/mnt/d/XBrainLabCache/rag
poetry run -- python run.py
```

不要靠未記錄的 shell state 判斷模型是否可用。Final handoff 只透過 canonical runner 綁定
explicit D-mounted cache；每筆 check 的 environment policy 以 redacted mount + path digest
記錄 identity。

目前 closure worktree 的 model cache 只包含 exact Granite snapshot，實際磁碟用量約
`5.07 GB`（`4.8 GiB`）；root checkout 的 historical cache 約 `12.77 GB`，還包含 retired Phi
內容。Desktop launcher 若仍指向 root checkout，就會看到後者；兩者都不能在未記錄 path、branch、
SHA、dirty state 與 model revision 時當成 handoff 事實。Catalog download estimate 是
`5.08 GB`。容量是本機狀態，handoff 前仍要以 runtime inspect / preflight 重查。產品只接受
exact Granite；Granite 不可用時會明確失敗，
不會靜默換成 Phi，Phi 也不能由產品 UI 選取。已刪除舊 Qwen cache；不要重新下載或使用
Qwen、DeepSeek、Yi、GLM、Baichuan、InternLM、MiniCPM 等中國公司或中國來源模型。

下載前檢查：

```bash
poetry run -- python scripts/dev/plan_local_model_download.py --format markdown
poetry run -- python scripts/dev/plan_local_model_download.py \
  --model ibm-granite/granite-3.3-2b-instruct --format markdown
```

已下載的模型會被視為 cached：preflight 應顯示 `ok=True`、estimated download `0.00 GB`，
projected cache 不會重複加上同一模型大小。

runtime health check：

```bash
poetry run -- python scripts/dev/inspect_local_assistant_runtime.py --format markdown
poetry run -- python scripts/dev/inspect_local_assistant_runtime.py \
  --format markdown --prompt-smoke --structured-smoke
poetry run -- python scripts/dev/inspect_local_assistant_runtime.py \
  --model ibm-granite/granite-3.3-2b-instruct \
  --format markdown --prompt-smoke --structured-smoke
```

清理模型 cache 時，只刪明確模型目錄與 lock，例如：

```bash
rm -rf \
  XBrainLab/llm/core/models/models--ibm-granite--granite-3.3-2b-instruct \
  XBrainLab/llm/core/models/.locks/models--ibm-granite--granite-3.3-2b-instruct
```

清理後重新跑 preflight，確認 projected cache 仍低於上限。

## Handoff Evidence

Final handoff 的相容入口會建立 full-handoff plan，再委派唯一 control plane 執行與驗證：

```bash
MODEL_CACHE_DIR="$(realpath XBrainLab/llm/core/models)"
RAG_CACHE_DIR=/mnt/d/XBrainLabCache/rag
CANDIDATE_BRANCH="$(git branch --show-current)"
git fetch --no-tags origin refs/heads/main:refs/remotes/origin/main
TARGET_SHA="$(git rev-parse refs/remotes/origin/main)"
poetry run -- python scripts/dev/run_handoff_validation_manifest.py \
  --model-cache-dir "$MODEL_CACHE_DIR" \
  --rag-cache-dir "$RAG_CACHE_DIR" \
  --expected-branch "$CANDIDATE_BRANCH" \
  --target-sha "$TARGET_SHA"
```

Runner 從 `scripts/dev/handoff_gate_spec.py` 讀取全部 required IDs，產生綁定 immutable target
SHA 的 plan，逐一交給 recorder，最後驗證完整 dossier。不要手動複製 validation 頁中的
individual commands 拼成 final result。兩個 cache
argument 都必須是 `/mnt/d/...` absolute path；runner 不接受 C 槽、WSL home 或 implicit default。
`TARGET_SHA` 是使用者授權的比較 target；canonical flow 先刷新 configured `origin` 的 main tip，
不能從未刷新或任意重指的 tracking ref 自行宣稱授權。若 PR 的正式 target 不是該 tip，改傳
reviewed PR/event 提供的 exact target SHA。

預設 evidence root 是 repo 內 gitignored 的 `build/handoff-evidence/<full-SHA>/`。若 evidence
必須放在 checkout 外，使用 absolute SHA-scoped root 並明確加入
`--allow-external-evidence-root`；external root 不需要也不應執行 repo-relative `git check-ignore`。
完整 policy 和 claim boundary 看 [Validation](validation/README.md)。

## 常用指令

安裝標準依賴：

```bash
poetry install --with dev,test,docs
```

啟動 app：

```bash
poetry run -- python run.py
```

建立文件站：

```bash
poetry run -- mkdocs build --strict
```

部署文件站：

- GitHub Pages workflow：`.github/workflows/docs-pages.yml`
- 觸發方式：push 到 `main`，或 GitHub Actions 內手動 `workflow_dispatch`
- publish source：GitHub Pages artifact，內容來自 build output `site/`

`site/` 仍是 build output，不手改、不 commit。GitHub repo settings 需要將 Pages source 設成
`GitHub Actions`，部署後網址由 workflow 的 `github-pages` environment 顯示。

刷新 fast quality dashboard：

```bash
poetry run -- python scripts/dev/update_quality_dashboard.py
```

跑 UI 測試 wrapper：

```bash
scripts/dev/run_ui_pytest.sh tests/unit/ui -q
```

跑 targeted pipeline smoke：

```bash
poetry run -- pytest --capture=sys \
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
