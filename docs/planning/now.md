# XBrainLab Now

最後更新：`2026-08-30`

## 目前焦點：Assistant dispatch / prompt iteration v1

唯一 active slice 是 `fix/assistant-clarification-capture-v1`，以
`69a1ea40492ad92b92a59fadb14a1163e60293f3` 為施工起點。目標不是讓 prompt
「看起來清楚」，而是讓真實 Granite 3B 在產品 context 中自己選對 action，並確保
Host 不以英文語法取代模型做 intent 判斷。

### Current implementation checkpoint: montage and channel publication lifecycle

#### Problem and evidence

- A real Assistant session requested montage three times and received `tools=0/0`; the model could
  not select the existing GUI handoff even though the GUI/backend montage capability is broader.
- The current stage projection publishes `set_montage` only after epochs, while `select_channels`
  disappears after `data_loaded`. That stage mismatch makes the assistant-facing lifecycle disagree
  with the intended pre-epoch workflow.

#### Outcome

`select_channels` and `set_montage` are published only at `data_loaded` and `preprocessed`.
They remain available after preprocessing, disappear immediately after successful epoch creation,
and are not published at `empty`, `epoch_ready`, `dataset_ready`, `training`, or `trained`.

#### Scope and non-goals

- Change only the existing Assistant `STAGE_CONFIG` projection in
  `XBrainLab/llm/pipeline_state.py`, its exact publication tests, the directly affected no-action
  evaluator case, and the canonical Complete Workflow order.
- Existing GUI/backend capabilities remain unchanged; montage remains broader after epochs. This
  slice does not change them. It also does not alter tool schemas, prompts, evaluator denominators, UI,
  model selection, or root `settings.json`.

#### Assumption, steps, and focused validation

The immutable ApplicationService publication remains the authoritative stage input; this is solely
the Assistant tool-surface projection. First make exact stage-membership tests red, then change the
mapping and align only direct contract consumers: pipeline/assembler publication tests, the
epoch-after-unavailable montage precision case, and Complete Workflow profile plus its canonical
walkthrough text. Run those focused tests, Ruff for touched Python, and `git diff --check`.

#### Stop condition and UI confirmation

Stop if the desired lifecycle requires changing backend/GUI capability, adding an owner, schema,
prompt heuristic, or a new state machine. UI confirmation: not applicable; this slice has no UI
edit.

### 問題與證據

- `I want to import data.` 被 import 的 positive-origin English matcher 擋成
  `intent_mismatch`，即使模型已提出 `import_eeg_data`。
- 完整的 `I want to do a bandpass filter and high is 40 Hz, low is 15 Hz.` 與
  `Use 100 Hz resample.` 被 direct-action English grammar 擋下；Host 把模型應負責的
  action recognition 搬進了 regex。
- 收齊 preprocess receipt 後，controller 又要求模型重送同一 JSON。真實 session 曾因
  這個多餘 generation 產生 prose / envelope failure，使用者明明補齊值卻不能執行。
- 現有 prompt 的單條規則可讀，但 `respond_to_user` 與 no-action fallback 重複出現，決策
  層級不清楚，會誘導模型教使用者「應呼叫哪個函式」而不是自己 dispatch。
- `335ca018` manual artifact 的 bandpass turn 已有模型提出的 `low_freq=10`、`high_freq=40`，且
  latest user text 含兩個 Arabic decimals；Host 卻因 `high filter is 40` 不符合 label regex
  只建立 partial receipt。下一輪自然補值含 `bandpass/filter` prose 又被 receipt value-shape
  regex 清除，導致模型被迫重試並提出 schema-incomplete action。

### Outcome

1. 模型選 tool；Host 不判斷 import intent、英文 action verb、negation 或 request grammar。
2. Host 對五個 direct preprocess tools 只驗證 latest user text 的 value provenance / shape，
   然後重跑既有 schema、range、fresh publication、capability、confirmation 與 command path。
3. receipt 收齊後，以 receipt 的 exact tool 與 verified values 直接進既有
   `ToolAttemptCoordinator → presentation / execution`；不得再呼叫 RAG 或 LLM。
4. Prompt 採 action-first 決策順序，明確禁止把 internal function/tool 呼叫責任推回使用者，
   且 fallback schema / no-action example 不重複。
5. 成功證據必須同時包含 fitted prompt、raw model output 與 product terminal，不能由人工閱讀
   prompt 或 Host rescue 宣稱改善。

### Scope

- 刪除 import positive-origin gate、direct English action matcher、`INTENT_BLOCKED` /
  `intent_mismatch`、receipt-to-prompt bridge 與 completed receipt 的第二次 model proposal。
- 限定五個 direct preprocess tools：bandpass、notch、resample、reference、normalization。
  action 與 low/high mapping 都由模型 proposal 決定；Host 對 bandpass 只檢查 latest user text
  是否包含同一 Arabic-decimal values，不解析 `bandpass`、`filter` 或英文 request grammar。
  首次純值 pair 仍以 min→low、max→high 收集；receipt 已有一個 field 時，一個 bare value
  只填其 sole remaining field。
- 保留 strict JSON parser、tool membership/schema、ApplicationService、confirmation、UI 與模型
  revision；不新增 module、owner、router、state machine 或 receipt type。
- Arabic decimal only；不加入 word-number parsing，不修改 UI 或 root `settings.json`。

### TDD / evidence loop

先加最小 red reproductions，再做 deletion-first repair。每輪由 Implementation Agent 修一個已證明原因；
User Agent 以黑箱正常入口記錄 prompt/raw/visible terminal；Reviewer 檢查模型是否真的 dispatch、Host
有沒有重建英文 intent router、以及 lifecycle 是否仍走既有 owner。Reviewer 不自行擴增極端案例。

固定中央情境：import、完整 bandpass、完整 resample、一般問題、否定 import、empty-stage epochs；
中央情境通過後，才跑五個 preprocess 的補值、切換 action、cancel 與 stale publication。任何清楚
action 回覆「應呼叫某函式」都是 `model_declined_required_action`，不可 handoff。

既有 81-case report 保留作歷史比較；新增 exact-SHA natural-dispatch / receipt lifecycle evidence，
raw model、Host 與 product outcome 分欄，不能靠 Host 加分。每一 source change 都使先前 manual
acceptance 失效。達 focused tests、review、CI 與 exact-SHA evidence 後才交使用者手測；使用者明確
手測通過並同意 merge 前不合併。

### Stop condition

若下一步只能靠新增英文 intent regex、放寬 strict JSON、替換模型、改 tool public contract 或新增
owner/state machine 才能通過，停止並回報；不得把這些擴張藏在 repair 裡。
