# 測試與驗證

如果只修改一個功能，先跑能直接觀察該功能的測試；不要一開始就跑全部測試。只有準備交付
候選版本時，才需要執行完整 handoff 驗證。

本頁所有命令都要在 repository root 執行。

## 我現在該跑哪一個？ { #choose-test }

先找出這次改動屬於哪一種情況：

| 這次改了什麼 | 先執行 | 接著看 |
| --- | --- | --- |
| 一個函式、錯誤或明確行為 | 直接覆蓋該行為的 pytest test file 或 test node | [只測這次修改](#focused-test) |
| Backend | Backend 測試集 | [命令與說明](#domain-test) |
| 桌面 UI | UI 測試集 | [命令與說明](#domain-test) |
| Assistant 或 tool call | LLM 測試集 | [三層 tool-call 測試](#tool-call-tests) |
| 文件或 MkDocs | 文件 portal build | [命令與說明](#docs-test) |
| 準備交付候選版本 | 完整 handoff manifest | [準備交付候選版本](#handoff) |

測試通過只代表該測試實際觀察到的行為通過。例如，unit test 通過不代表真人操作 GUI 已通過，
真模型選對工具也不代表工具已成功執行。

## 每次開始前都先確認

```bash
git status --short --branch
git diff --check
```

第一條命令用來確認目前 branch，以及工作區內是否已有別人的修改。第二條命令會檢查 diff 的
空白與 patch 格式問題。

Root `settings.json` 是使用者本機的 runtime 設定。不要 stage、revert 或隱藏它，也不要為了讓
工作區看起來乾淨而覆寫它。

## 只測這次修改 { #focused-test }

知道是哪個 test file 時，直接執行該檔案：

```bash
poetry run python -m pytest --capture=sys tests/path/test_file.py -q
```

只想執行其中一個 test 時，在檔名後加上 test 名稱：

```bash
poetry run python -m pytest --capture=sys \
  tests/path/test_file.py::test_name -q
```

上面的 `tests/path/test_file.py` 和 `test_name` 都是範例，必須換成這次實際修改所對應的測試。
優先選擇「若這次改壞就會失敗」的測試，而不是只碰巧執行到相關程式碼的測試。

Qt、MNE、PyTorch 等 native library 有機會讓程序直接中止。在 Linux 或 WSL 執行這類測試時，
加入 10 分鐘 timeout，並停用 core dump：

```bash
timeout 10m prlimit --core=0 -- \
  poetry run python -m pytest --capture=sys tests/path/test_file.py -q
```

## 測整個功能區 { #domain-test }

Repository runner 會替容易發生 native crash 的測試設定 headless 環境、程序隔離和 timeout。
先選與這次改動相符的一個功能區：

| 功能區 | 命令 |
| --- | --- |
| Backend command 與 service | `poetry run python scripts/dev/run_tests.py backend` |
| Qt UI | `poetry run python scripts/dev/run_tests.py ui` |
| Assistant、LLM 與 tool-call contract | `poetry run python scripts/dev/run_tests.py llm` |

需要檢查更大的測試集合時，再使用下列命令：

```bash
poetry run python scripts/dev/run_tests.py unit
poetry run python scripts/dev/run_tests.py integration
poetry run python scripts/dev/run_tests.py regression
```

`all` 會依序執行 unit、integration 和 regression，因此時間較長：

```bash
poetry run python scripts/dev/run_tests.py all
```

即使 `all` 通過，也不代表 GUI 已由真人操作驗收，或候選版本已達到 handoff-ready。若要查看
runner 目前支援的選項，執行：

```bash
poetry run python scripts/dev/run_tests.py --help
```

## 檢查 Python 程式碼品質

把範例路徑換成本次修改的 Python 檔案：

```bash
poetry run ruff check path/to/changed.py tests/path/test_changed.py
poetry run ruff format --check path/to/changed.py tests/path/test_changed.py
poetry run python scripts/dev/run_basedpyright_regression.py
git diff --check
```

- `ruff check`：檢查 lint 問題。
- `ruff format --check`：檢查格式，但不修改檔案。
- `run_basedpyright_regression.py`：確認型別檢查沒有增加新的 diagnostic。
- `git diff --check`：檢查 diff 的空白與 patch 格式。

Basedpyright runner 會使用 repository 內已提交的 allowlist。不要用型別分析器自動產生的新
baseline 取代它，否則可能把新問題一起接受進去。

## 測文件網站 { #docs-test }

修改 user guide、工程文件、`mkdocs.yml` 或 portal builder 時，依序執行：

```bash
poetry run python scripts/dev/validate_user_site.py
poetry run python scripts/dev/build_docs_portal.py
poetry run python scripts/dev/validate_user_site.py \
  --built-dir build/dev-artifacts/docs-portal-review/guide
```

三條命令分別檢查：

1. User guide 的來源檔案與導覽結構。
2. 工程站和 user guide 能否以 strict mode 建置，且本機連結、Material assets 與 search index
   是否完整。
3. 建置後的 `/guide/` 輸出是否仍符合 user-site contract。

若修改的是 `AGENTS.md`、repo-local skills 或 workflows，另外執行：

```bash
poetry run python scripts/dev/audit_agent_guidance.py check --format json
```

## 測 Assistant tool call { #tool-call-tests }

Tool-call 測試分成三層，回答的是三個不同問題：

| 層級 | 回答的問題 | 是否載入 Granite | 是否真的執行工具 |
| --- | --- | --- | --- |
| A. Contract 測試 | 工具清單、JSON、參數檢查與執行邊界是否正確？ | 否 | 測試依案例而定 |
| B. 真模型選擇評分 | Granite 面對固定 prompt 時，是否選對工具並填對參數？ | 是 | 否 |
| C. GUI 操作檢查 | 確認、取消、handoff、結果顯示和完整互動是否正確？ | 視命令而定 | 是 |

不要把其中一層的結果當成另外兩層的證據。

### A. 不載入模型：先檢查 contract

先執行 Assistant 測試集，以及固定案例、評分器與 GUI walkthrough profile 的單元測試：

```bash
poetry run python scripts/dev/run_tests.py llm
poetry run python -m pytest --capture=sys \
  tests/unit/scripts/test_stable_assistant_model_eval.py \
  tests/unit/scripts/test_agent_walkthrough_profiles.py -q
```

這一層會檢查目前 18 個可執行 action 的名稱、stage 和 JSON schema，也會檢查非工具決策
`respond_to_user`、參數防護、確認流程和結構化結果。也就是說，模型是在「回覆使用者」或
「選擇一個可執行 action」之間做決定；`respond_to_user` 本身不屬於 18 個可執行 action。

因為 Granite 沒有在這裡回答 prompt，所以這些測試不能證明真模型的工具選擇正確率。

若修改了 backend admission、錯誤恢復或執行邊界，再執行這組 integration test：

```bash
timeout 30m prlimit --core=0 -- \
  env QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true \
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  poetry run python -m pytest --capture=sys \
  tests/integration/agent/test_product_flow.py \
  tests/integration/agent/test_strict_recovery_execution_boundary.py -q
```

### B. 載入 Granite：評分工具選擇

這個評分會真的讓 Granite 回答固定 prompt，但不會執行模型選出的工具。

執行前先確認 active decision 指定的 Granite 3.3 2B 已存在 D-mounted cache。將下列兩個範例
路徑換成本機實際位置：

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

`HF_HUB_OFFLINE=1` 和 `TRANSFORMERS_OFFLINE=1` 會禁止執行期間下載模型，也不允許靜默改用另一個
模型。

目前 runner 固定執行 50 個案例：36 個 positive cases 和 14 個 challenge cases。候選 gate 要求：

- 36/36 positive cases 的工具與參數完全正確。
- 10/10 明確參數來源檢查通過。
- 5/5 缺少參數時的 host guard 通過。

其餘 challenge 結果用來記錄模型限制，不計入上述候選 gate。產生的 JSON report 只支持該次
使用的 exact model、revision、source 和 50 個固定案例；它不能證明任意對話、工具實際執行或
論文等級的整體正確率。

### C. 打開 GUI：檢查實際互動

`--tool-debug` 會用正常的 ChatPanel 和 MainWindow 路徑顯示工具呼叫，但不建立或載入 Granite。
目前有五份 GUI walkthrough profile：

| Profile | 主要檢查內容 |
| --- | --- |
| Response Presentation | Assistant 回覆 bubble，以及回覆後的 panel navigation |
| Contract Failures | 前置條件不足時的 blocked 結果，以及 blocked 後能否繼續操作 |
| GUI Cancellation Recovery | 使用者取消 dialog 後，GUI 是否回到可操作狀態 |
| Complete Workflow | Dataset、Preprocess、Training、Evaluation 到 Visualization 的完整流程 |
| Lifecycle / Routing | Start、Stop、Clear、Reset，以及各 panel 和 visualization route |

每次只選一份 profile，使用新的 process 和 session。以下五條都是可直接從 repository root
啟動 GUI 的命令。

檢查一般回覆 bubble 與後續 navigation：

```bash
poetry run python run.py \
  --tool-debug scripts/dev/agent_tool_walkthrough/response-presentation.json
```

檢查 blocked、失敗顯示與錯誤後恢復：

```bash
poetry run python run.py \
  --tool-debug scripts/dev/agent_tool_walkthrough/contract-failures.json
```

檢查取消 dialog 後能否恢復操作：

```bash
poetry run python run.py \
  --tool-debug scripts/dev/agent_tool_walkthrough/gui-cancellation.json
```

檢查從資料匯入到 saliency 的完整 GUI workflow：

```bash
poetry run python run.py \
  --tool-debug scripts/dev/agent_tool_walkthrough/complete-workflow.json
```

檢查 training lifecycle、reset 與所有主要 route：

```bash
poetry run python run.py \
  --tool-debug scripts/dev/agent_tool_walkthrough/lifecycle-routing.json
```

XBrainLab 開啟後，依畫面顯示的目前 step 操作，而且每個 step 只送出一次。Dialog、confirmation、
navigation 或 training 尚未顯示 terminal 結果時，不要進到下一步。若畫面不符合預期，記錄
step ID 和 screenshot 後停止該次 session。

Profile JSON 是實際步驟順序的權威來源；完整的人工驗收條件與 Complete Workflow 測試資料設定
見[Assistant 人工操作驗證](../validation/README.md#assistant-manual-walkthrough-commands)。

若要讓真 Granite 經由可見的 ChatPanel 執行 Data Interpretation 的
scan → preview → validate，使用：

```bash
MNE_DONTWRITE_HOME=true \
HF_HUB_OFFLINE=1 \
TRANSFORMERS_OFFLINE=1 \
timeout 10m prlimit --core=0 -- \
  poetry run python scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py \
  --model ibm-granite/granite-3.3-2b-instruct \
  --output-dir build/dev-artifacts/chatpanel-local-tool-chain
```

這個命令需要可見的 Qt display。為了產生可重複比較的截圖，它會清除 XBrainLab 儲存的主視窗
位置與大小，並在 `build/dev-artifacts/` 寫入 transcript、JSON 和 screenshots。它只檢查三個
指定 action，不代表全部 18 個可執行 action 都完成端到端驗證。

## 準備交付候選版本 { #handoff }

這不是日常開發命令。只有要宣稱某個 exact commit 已經 handoff-ready 時才執行完整 manifest。

Runner 會要求來源已 commit、工作區狀態符合規則，而且 exact source 已 push。先填入實際 cache
路徑和候選 branch：

```bash
export XBRAINLAB_MODEL_CACHE_DIR=/mnt/d/path/to/model-cache
export XBRAINLAB_RAG_CACHE_DIR=/mnt/d/path/to/rag-cache
export XBL_CANDIDATE_BRANCH=feature/example

poetry run python scripts/dev/run_handoff_validation_manifest.py \
  --model-cache-dir "$XBRAINLAB_MODEL_CACHE_DIR" \
  --rag-cache-dir "$XBRAINLAB_RAG_CACHE_DIR" \
  --expected-branch "$XBL_CANDIDATE_BRANCH"
```

完整 gate 清單的唯一權威來源是 `scripts/dev/handoff_gate_spec.py`，不要把其中的命令複製到其他
文件後自行刪減。若 required gate 缺少、不同 gate 使用不同 SHA、CI 尚未成功，或必要的人工驗收
不存在，就不能宣稱 handoff-ready。

## 怎麼回報測試結果

測試回報至少要回答五件事：

1. 執行了哪一條命令和哪個 test selector。
2. 命令是否成功，以及通過／失敗數量。
3. 測試對應哪一個 branch、commit，工作區是否有未提交修改。
4. 是否有環境限制，例如沒有 GPU、沒有可見 Qt display 或使用 offline mode。
5. 結果能證明什麼，以及明確不能證明什麼。

一般 focused test 不需要另外建立永久 receipt；只有驗證契約明確要求時才保存 artifact。
