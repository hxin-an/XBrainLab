# XBrainLab 目前狀態

最後更新：`2026-05-02`

## 摘要

XBrainLab 的 active repo 已在目前 workspace 專案區。標準 `dev,test,docs` 環境可用，fast quality dashboard 已在新路徑刷新，結果是 clean `PASS`。

目前階段已進入 product-delivery engineering，但 `2026-05-02` 人工驗收修正了先前的
產品判斷：AI Assistant 仍有 release blocker。使用者實際打開 assistant 後發現 chat UI
仍像 debug dock，且一般輸入 `hello` 後沒有任何 assistant 回覆。這代表先前 automated
final gate、local runtime smoke、launcher startup smoke、deterministic eval 都不能被解讀成
「可用桌面產品已完成」。

後端 `ApplicationService / Command API` 第一版已落地，並完成 command contract、
capability policy、reset state invalidation 和 facade compatibility 的驗收補強。UI / Agent
command surface 第一批統一也已完成：UI readiness 和 agent tool availability 都開始讀同一套
ApplicationService capability policy，agent tool result 已收斂成 typed adapter。local LLM
runtime 已完成非中國 primary / fallback 模型選型、cache preflight、下載、GPU prompt smoke
和 structured-output smoke；desktop launcher 已產出並完成 startup smoke。

目前真正的 product gate 剛被 chat response reliability 和 chat UX 擋住；本輪已完成 targeted
修復與 tests：normal text input 有可見 assistant 回覆、空回覆 / worker error / local
unavailable 有可見狀態、ChatPanel 已從 debug dock 改成產品化面板。broader UI / LLM gate
已重跑通過；真 local model / Windows launcher click-through walkthrough 仍待驗收，完成前不能
重新宣稱完整 product delivery。

## 可信狀態

- active repo：`/mnt/d/workspace_v2/projects/lab/XBrainLab`
- 舊 repo 副本：`/mnt/d/repos/XBrainLab`，目前只作 archive / reference。
- branch：`codex/stabilization-autopilot`
- remote：`https://github.com/hxin-an/XBrainLab.git`
- docs 已收斂成 `target/`、`architecture/`、`planning/`、`decisions/`、`validation/`、`records/`，根層只保留入口與目前狀態 / 操作文件。
- root `ROADMAP.md` 已刪除；目前路線只看 `docs/planning/roadmap.md`。
- `CHANGELOG.md` 只保留歷史版本紀錄，不作 current truth。
- 標準 Poetry env 已安裝 `dev,test,docs` dependency group：
  - `/home/administrator/.cache/pypoetry/virtualenvs/xbrainlab-TKrzxeIe-py3.12`
- import probe 已通過：
  - `PIL 12.1.0`
  - `mne 1.11.0`
  - `PyQt6`
  - `torch 2.11.0+cu130`
  - `pytest 8.4.2`
  - `XBrainLab 0.5.6`
- 文件站點已可用：
  - `poetry run mkdocs build --strict`
- local assistant runtime 已可用：
  - primary：`microsoft/Phi-4-mini-instruct`
  - fallback：`microsoft/Phi-3.5-mini-instruct`
  - cache：`XBrainLab/llm/core/models`
  - current cache usage：約 `15.34 GB`
  - Qwen cache 已刪除；中國公司或中國來源模型不列入選型。
- 桌面 launcher 已產出：
  - repo source：`scripts/launchers/xbrainlab_wsl_launcher.cmd`
  - repo source：`scripts/launchers/xbrainlab_wsl_launcher.ps1`
  - Windows Desktop：`/mnt/c/Users/Administrator/Desktop/XBrainLab.cmd`

## 品質門檻

最新 fast dashboard：

- generated at：`2026-05-02 12:29:06 UTC+08:00`
- workspace：`/mnt/d/workspace_v2/projects/lab/XBrainLab`
- overall：`PASS`
- 來源：`artifacts/quality/latest.json`、`artifacts/quality/latest.md`

當時全部 gate 都是 `PASS`：

- Ruff Lint
- Basedpyright
- Architecture Compliance
- Startup Smoke
- UI Baseline Capture
- UI Dialog Acceptance
- UI Unit Suite
- Real-Data IO Integration

補充已知通過項目：

- backend Application Service / facade contract suite：
  - `poetry run pytest --capture=sys tests/unit/backend/application -q`
  - `9 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q`
  - `2 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
  - `44 passed`
- UI unit suite：
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - `817 passed`
- LLM unit suite：
  - `poetry run pytest --capture=sys tests/unit/llm -q`
  - `652 passed`
- agent tool/control suite：
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
  - `321 passed`
- backend unit suite：
  - `poetry run pytest --capture=sys tests/unit/backend -q`
  - `2661 passed, 1 skipped, 1 xfailed`
- backend + IO integration：
  - `poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q`
  - `33 passed`
- full pipeline integration：
  - `poetry run pytest --capture=sys tests/integration/pipeline -q`
  - `70 passed`
- local assistant runtime smoke：
  - preflight：
  - `poetry run python scripts/dev/plan_local_model_download.py --format markdown`
  - primary already cached；estimated download `0.00 GB`；projected cache `15.34 GB`
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown --prompt-smoke --structured-smoke`
  - primary prompt smoke：`passed`
  - primary structured-output smoke：`passed`
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --model microsoft/Phi-3.5-mini-instruct --format markdown --prompt-smoke --structured-smoke`
  - fallback prompt smoke：`passed`
  - fallback structured-output smoke：`passed`
- startup smoke：
  - `timeout 45s xvfb-run -a poetry run python run.py --model local`
  - `MainWindow initialized` 後 timeout 結束，屬於 GUI smoke 預期結果。
- tool-call eval deterministic baseline：
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals`
  - artifacts：`artifacts/agent_evals/latest.json`、`artifacts/agent_evals/latest.md`
  - `21 / 21` cases passed；deterministic baseline，不是 local LLM performance claim。
- `ai-assistant-open.png` 的 `(1684, 800)` product redesign baseline 已接受，尺寸和
  live artifact、repo HEAD reference 一致。

## 邊界與未驗證事項

- `docs/legacy/` 已整合後刪除。
- `docs/active/` 已收掉；canonical 文件直接放在 `docs/` 根層。
- `.agents/legacy/` 已整合後刪除；現行 agent 操作層只剩 `.agents/stack.md`、runbooks、context。
- 舊文件裡的 `/mnt/d/repos/XBrainLab` 絕對路徑不代表現在 active path。
- thesis / agent performance claim 不能只靠 engineering dashboard 支撐。
- local transformer runtime 已以 primary / fallback model smoke 驗證；4-bit / bitsandbytes
  仍是 optional path，不是預設產品依賴。
- agent runtime 的目標方向是 local-only；目前 code 仍殘留 API / Gemini 相關路徑，這些路徑是本輪之後要隔離或移除的產品殘留，不能宣稱已完成 local-only。

## 目前 blocker

目前舊 final gate 判定已失效，不能用它宣稱 product delivery 完成：

- AI Assistant 一般輸入 `hello` 曾出現 silent no-response；本輪已補 visible-response contract
  和 deterministic product-flow test。
- ChatPanel 視覺曾偏 debug dock；本輪已完成第一輪產品化 redesign。
- automated gate 漏掉了最基本的 user-visible chat product flow。deterministic eval `21 / 21`、
  local prompt smoke、launcher startup smoke 都不能替代真 chat flow 驗收。
- broader UI / LLM gate 已針對本輪修復重跑通過；真 launcher / local model walkthrough 尚未完成。

仍存在的非阻塞架構風險：

- UI action execution 仍有不少直接 controller path。
- 部分 assistant real tools 仍先走 `BackendFacade` legacy method 再由 typed adapter 正規化結果。
- launcher 尚未完整做人工 click-through 互動驗收。
- `evaluate` / `visualize` / `saliency` / `new_session` 仍只是 disabled future command contract。
- tool-call eval 目前只有 deterministic baseline，尚未跑 local LLM primary / fallback 真實 agent runner。

## 目前執行中

1. 做本輪 chat product fix checkpoint commit。
2. 接著回到更多 UI action execution command adapter、launcher click-through、query command contract。

## 相關文件

- [target/README.md](target/README.md)
- [planning/now.md](planning/now.md)
- [operations.md](operations.md)
- [validation/README.md](validation/README.md)
