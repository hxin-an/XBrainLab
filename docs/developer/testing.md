# 測試與驗證

先選擇能直接觀察本次變更的最小測試，再決定是否需要擴大到 subsystem、真模型或完整
handoff。測試通過只支持它實際觀察到的行為，不會自動證明整套產品、科學品質或真人操作。

所有命令都從 repository root 執行。

## 開始前確認 source

```bash
git status --short --branch
git diff --check
```

先確認 branch、既有 dirty files 與本次 scope。Root `settings.json` 是本機 runtime 設定，不得
stage、revert 或藏起來換取 clean status。

## 選擇測試層級

| 層級 | 適合使用時機 | 不能單獨證明 |
| --- | --- | --- |
| Focused test | 一個 behavior、defect 或 state transition | 相鄰 subsystem 或完整 workflow |
| Domain runner | Backend、UI、LLM 或完整 unit／integration family | 真人 GUI、real dataset diversity |
| Docs build | 導覽、連結、search index 與網站輸出 | 產品 runtime 行為 |
| Local model eval | 固定模型對 frozen tool-call cases 的輸出 | Tool execution、完整 UI workflow、thesis accuracy |
| Handoff manifest | 同一 exact source 的完整工程 dossier | 使用者 manual acceptance 或科學認證 |

## 執行 focused test

單一 test file 或 test node：

```bash
poetry run python -m pytest --capture=sys tests/path/test_file.py -q
poetry run python -m pytest --capture=sys tests/path/test_file.py::test_name -q
```

把範例 selector 換成會直接失敗於本次 defect 或 contract 的真實 selector。Qt、MNE、PyTorch 或
其他可能 native abort 的 Linux／WSL 測試，加入明確 timeout 並停用 core dump：

```bash
timeout 10m prlimit --core=0 -- \
  poetry run python -m pytest --capture=sys tests/path/test_file.py -q
```

不要只用 mock-heavy test 宣稱 native GUI、真實 dataset 或本機模型已經完成。

## 執行 domain suite

Repository runner 會為 native-heavy domains 設定 headless 環境、process isolation、timeout 與
pytest completion attestation。每次只選與變更相符的最小 command：

```bash
poetry run python scripts/dev/run_tests.py backend
poetry run python scripts/dev/run_tests.py ui
poetry run python scripts/dev/run_tests.py llm
poetry run python scripts/dev/run_tests.py unit
poetry run python scripts/dev/run_tests.py integration
poetry run python scripts/dev/run_tests.py regression
```

`all` 會依序執行 unit、integration 與 regression，成本高於一般 focused change，而且仍不等於
handoff-ready：

```bash
poetry run python scripts/dev/run_tests.py all
```

可用 command 與 selector ownership 以 runner 的 help 和 source 為準：

```bash
poetry run python scripts/dev/run_tests.py --help
```

## 靜態品質

只檢查本次修改的 Python paths：

```bash
poetry run ruff check path/to/changed.py tests/path/test_changed.py
poetry run ruff format --check path/to/changed.py tests/path/test_changed.py
poetry run python scripts/dev/run_basedpyright_regression.py
git diff --check
```

Basedpyright runner 以 checked-in allowlist 判斷是否增加 diagnostic；不要用 analyzer 自動改寫的
baseline 取代它。

## 文件網站

修改 user guide、engineering docs、MkDocs 設定或 portal builder 時：

```bash
poetry run python scripts/dev/validate_user_site.py
poetry run python scripts/dev/build_docs_portal.py
poetry run python scripts/dev/validate_user_site.py \
  --built-dir build/dev-artifacts/docs-portal-review/guide
```

Portal builder 會以 strict mode 建置兩站，組成 `/` 與 `/guide/`，再檢查 local URLs、Material
assets 與兩份 search index。修改 `AGENTS.md`、skills 或 workflows 時另跑：

```bash
poetry run python scripts/dev/audit_agent_guidance.py check --format json
```

## Tool-call 測試

Tool-call 有三種不同層級。請在結果中寫清楚使用哪一層，以及它不能支持的 claim。

### 1. Deterministic contract

先跑 Assistant unit domains，再驗證 frozen cases、scorer 與 walkthrough profile contract：

```bash
poetry run python scripts/dev/run_tests.py llm
poetry run python -m pytest --capture=sys \
  tests/unit/scripts/test_stable_assistant_model_eval.py \
  tests/unit/scripts/test_agent_walkthrough_profiles.py -q
```

需要檢查 backend-owned admission、recovery 與 execution boundary 時，使用 focused integration
checkpoint：

```bash
timeout 30m prlimit --core=0 -- \
  env QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true \
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  poetry run python -m pytest --capture=sys \
  tests/integration/agent/test_product_flow.py \
  tests/integration/agent/test_strict_recovery_execution_boundary.py -q
```

這一層可驗證 strict envelope、current model-facing projection、parameter guard、confirmation 與
structured result contract；因為沒有讓 Granite 回答 frozen prompts，不能稱為真模型 tool-call
accuracy。

### 2. 真 Granite selection eval

先確認 active decision 指定的 Granite 3.3 2B 已存在於 D-mounted cache，且 model／RAG cache 路徑
符合容量與 privacy policy。這個 command 強制 offline，不會下載或 silent fallback：

```bash
export XBRAINLAB_MODEL_CACHE_DIR=/mnt/d/path/to/model-cache
export XBRAINLAB_RAG_CACHE_DIR=/mnt/d/path/to/rag-cache

MNE_DONTWRITE_HOME=true \
HF_HUB_OFFLINE=1 \
TRANSFORMERS_OFFLINE=1 \
timeout 30m prlimit --core=0 -- \
  poetry run python scripts/dev/run_stable_assistant_model_eval.py \
  --device cuda \
  --strict \
  --json-out build/dev-artifacts/stable-assistant-model-eval.json
```

目前 runner 固定執行 50 cases：36 個 positive 與 14 個 challenge。Candidate gate 要求 36/36
positive exact tool＋parameters、10/10 explicit parameter-origin guards 與 5/5 missing-parameter
host guards；其餘 raw challenge 保留為 diagnostic limitations。

這份 report 只支持該 exact model、revision、source、case set 與 deterministic guard 的 bounded
selection 結論，不支持完整 tool execution、任意長 session 或 thesis-grade accuracy。

### 3. GUI 與 terminal behavior

Model-free `--tool-debug` 使用正常 ChatPanel／MainWindow 路徑測 confirmation、GUI handoff、cancel、
recovery 與 visible terminal，不會建立或載入 Granite：

```bash
poetry run python run.py \
  --tool-debug scripts/dev/agent_tool_walkthrough/contract-failures.json
poetry run python run.py \
  --tool-debug scripts/dev/agent_tool_walkthrough/complete-workflow.json
```

其他 approved profiles 與人工 step contract 見[驗證策略](../validation/README.md#assistant-manual-walkthrough-commands)。

若要讓真 Granite 經過 visible ChatPanel 執行 Data Interpretation 的 scan → preview → validate，
使用本機 tool-chain capture：

```bash
MNE_DONTWRITE_HOME=true \
HF_HUB_OFFLINE=1 \
TRANSFORMERS_OFFLINE=1 \
timeout 10m prlimit --core=0 -- \
  poetry run python scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py \
  --model ibm-granite/granite-3.3-2b-instruct \
  --output-dir build/dev-artifacts/chatpanel-local-tool-chain
```

這個 command 需要可見 Qt display，會為可重複截圖清除 XBrainLab 儲存的 main-window geometry，並在
`build/dev-artifacts/` 寫入 transcript、JSON 與 screenshots。它只覆蓋三個指定工具，不等於完整
18-action workflow。

## 完整 handoff

只有要宣稱 candidate handoff-ready 時才執行完整 manifest。Runner 要求 clean、pushed exact source，
並從唯一 registry 取得 gate argv、timeout、environment 與 artifact contract：

```bash
export XBRAINLAB_MODEL_CACHE_DIR=/mnt/d/path/to/model-cache
export XBRAINLAB_RAG_CACHE_DIR=/mnt/d/path/to/rag-cache
export XBL_CANDIDATE_BRANCH=feature/example

poetry run python scripts/dev/run_handoff_validation_manifest.py \
  --model-cache-dir "$XBRAINLAB_MODEL_CACHE_DIR" \
  --rag-cache-dir "$XBRAINLAB_RAG_CACHE_DIR" \
  --expected-branch "$XBL_CANDIDATE_BRANCH"
```

不要複製或手動縮減 `scripts/dev/handoff_gate_spec.py` 的 command list。缺少 required gate、使用
不同 SHA、pending／skipped CI 或沒有適用的 manual acceptance 時，只能回報 checkpoint 或 blocked。

## 回報結果

至少記錄 command、selector、exit status、source identity、環境限制，以及結果支持和不支持的
claim。一般 focused run 不需要建立永久 receipt；只有 evidence contract 明確要求時才保存 artifact。
