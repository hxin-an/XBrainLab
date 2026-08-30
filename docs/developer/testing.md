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

在載入模型前，可先輸出一個只使用checked-in synthetic case與pinned tokenizer的Markdown dossier。它會完整
保留`ContextAssembler` raw messages、`LocalBackend` processed messages，以及runtime context-fit後真正會送進
`generate_stream`的prompt；不載入model weights：

```bash
poetry run python scripts/dev/export_assistant_prompt.py \
  --case-id clarify_notch_en \
  --out build/dev-artifacts/assistant-prompt-review/clarify_notch_en.md
```

每份dossier都標記HEAD SHA與clean/dirty source state；dirty prompt不可以被誤稱為該HEAD的exact artifact。

### Opt-in runtime prompt capture

要擷取 GUI 實際送入本機模型的 fitted prompt 與 raw output，啟動前明確設定絕對路徑：

```bash
export XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR="$PWD/build/dev-artifacts/assistant-runtime-prompts"
```

每次 generation（包括 retry）會在 child-local session 的遞增序號目錄寫入
`prompt.txt`、`raw-output.txt` 與 `metadata.json`。未設定旗標時不做 capture I/O；capture 寫入失敗不會影響
模型推論。artifact 可能包含 chat、檔案路徑和 dataset／subject metadata。`build/` 被 Git ignore **不代表保密**：
只能選受控本機目錄，不要納入 support bundle 或上傳，完成後由操作者人工刪除。

所有 active first-turn cases（36 positive、14 challenge、24 no-action precision）都會經同一個
`ApplicationViewPublication` fixture 與 `ContextAssembler.get_messages`。dossier中的 state card、不可用
action projection與 LocalBackend role boundary 因此是產品路徑，而不是 evaluator 手組的 stage catalog。
36-case count維持不變；`start_training`改由最小可呼叫的`dataset_ready` fixture產生，故v9結果不可與舊有
把它手組在`epoch_ready`的結果直接比較。

執行前先確認 active decision 指定的 Granite 4.0 Micro 3B exact revision已存在active model cache。將下列兩個範例
路徑換成本機實際位置：

先用`nvidia-smi`確認3B evaluator啟動前至少約有8 GiB可用VRAM；不足時停止並等待資源釋放，不終止
不是本次驗證啟動的程序，也不要把OOM／資源不足寫成模型品質回歸。以下命令不會silent fallback到CPU或
另一個model。

```bash
export XBRAINLAB_MODEL_CACHE_DIR=/mnt/d/path/to/model-cache
export XBRAINLAB_RAG_CACHE_DIR=/mnt/d/path/to/rag-cache

MNE_DONTWRITE_HOME=true \
HF_HUB_OFFLINE=1 \
TRANSFORMERS_OFFLINE=1 \
timeout 30m prlimit --core=0 -- \
  poetry run python scripts/dev/run_stable_assistant_model_eval.py \
  --device cuda \
  --json-out build/dev-artifacts/stable-assistant-model-eval.json
```

`HF_HUB_OFFLINE=1` 和 `TRANSFORMERS_OFFLINE=1` 會禁止執行期間下載模型，也不允許靜默改用另一個
模型。上面的非strict模式會完整產生report，即使Stable promotion gate未過也不把已知限制偽裝成runner
故障；只用於bounded baseline比較。只有要判定Stable promotion時才加入`--strict`，canonical handoff
registry也維持strict模式。

目前v12 runner固定執行81個英文案例：36個positive、14個challenge、24個no-action precision與
7個controller-backed clarification trajectories。`case_summaries.core`、`precision`與`clarification`
各自保留其分母，`case_summaries.total`只表示81-case inventory完整性；raw model、post-recovery diagnostic、
Host safety、direct admission、product outcome與overall pass都位於獨立`candidate_gate`。Host block或format
recovery只能證明產品安全，不能增加first-generation raw model分數。候選 gate 要求：

- 36/36 positive cases 的工具與參數完全正確。
- 10/10 明確參數來源檢查通過。
- 5/5 缺少參數時的 host guard 通過；raw model本身必須追問正確缺少欄位。
- 24/24 no-action precision outcomes沒有confirmation、GUI handoff、execution或state mutation。
- 7/7 clarification trajectories經production controller抵達verified execute boundary：五個direct
  preprocess continuation、generic filter選擇bandpass後再追問，以及bandpass先low再high的partial
  accumulation；raw第一發與最多兩次format recovery分開記錄。

challenge的tool／stage／parameter／continuation／safety錯誤為零；最多三個非關鍵回覆措詞問題會完整列出。
產生的 JSON report 只支持該次
使用的 exact model、revision、source 和81個固定案例；它不能證明任意對話、工具實際執行或
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

### D. Windows native：Assistant bounded baseline

這份清單專門驗收inline setup、輸入、短bubble與bounded Granite行為；offscreen test、tool-debug profile或
自動capture都不能取代。開始前在候選branch執行`git rev-parse HEAD`並記下完整SHA；手測期間source若再改，
本次結果失效。使用拋棄式測試資料，不對重要資料執行已知誤操作案例。

從repository root啟動正常產品：

```bash
poetry run python run.py --model local
```

依序檢查：

1. 開啟Assistant Settings。Model清單必須同時有`Granite 4.0 Micro 3B (Recommended)`與
   `Granite 3.3 2B (Lower memory)`；選擇3B並完成既有cache／download流程。
2. 第一次打開Assistant Dock只能看到`Start XBrainLab Assistant` inline setup，不得出現
   `Local Assistant Runtime` modal。Cache完整時`Enable Assistant`可按；缺cache時`Set up model`與
   `Assistant Settings`都能回到唯一Settings流程。
3. 在空composer連按多次Space。對話不得被清除、不得開New Chat；接著送出`hello`，assistant的短回覆
   bubble要貼合內容，不得在文字後留下大片空白。
4. 使用Microsoft Pinyin輸入中文，以Enter選字。候選字commit時不得提前送出、不得遺失中文；組字完成後
   再按一次Enter，該訊息只能送出一次。Assistant terminal後，若沒有點到其他控制，focus應回composer；
   若手動把focus移到其他控制，Assistant不得搶回。
5. 用完整單一要求`Apply a 12 to 40 Hz bandpass filter`確認既有confirmation／GUI workflow仍可到達，
   但不要把confirmation、dialog或working-copy mutation誤寫成raw EEG被覆寫。
6. 診斷多輪路徑：輸入`Filter the data`→`Use a bandpass filter`→`12 to 40 Hz`，再於New Chat輸入
   `Apply a bandpass filter`→`12 to 40 Hz`。記錄每輪terminal與是否只產生一個bounded action；以同一SHA的
   v9 report和prompt dossier判讀，不將Host receipt或format recovery當成模型自行續接的證據。
7. 在對應安全stage重現`Create EEG epochs.`、`Please process this EEG data.`、
   `Apply a 4 to 38 Hz bandpass and then resample to 128 Hz.`與`Set average reference and normalize with
   z-score.`。記錄response、confirmation／handoff與bounded action；必要時取消dialog／confirmation。

Modal、按鈕不可用、Space清對話、中文無法commit／重複送出、focus被搶、短bubble尾端空白、完整單一
action回歸、crash、資料損失、跨New Chat／Stop／Close繼承receipt或失控重複執行都算失敗並停止。第6、7步
若只重現exact report已列出的bounded limitation則記錄但不阻擋baseline merge；任何更差結果仍阻擋。
通過後回報日期、完整SHA、實測範圍與Windows輸入法；只有同一SHA的明確通過回報、已知限制接受與merge
批准，才能完成PR／merge。

若要讓真 Granite 經由可見的 ChatPanel 執行 Data Interpretation 的
scan → preview → validate，使用：

先在正常產品的 Assistant Settings 選好 Granite 4.0 Micro 3B，確認模型cache完整並完成一次
`Enable Assistant`。Capture不會代替使用者同意啟用，也不會覆寫model selection；若仍顯示inline setup，
它會fail closed並要求先回Settings完成設定。

```bash
MNE_DONTWRITE_HOME=true \
HF_HUB_OFFLINE=1 \
TRANSFORMERS_OFFLINE=1 \
timeout 10m prlimit --core=0 -- \
  poetry run python scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py \
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
