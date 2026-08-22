# XBrainLab Agent Benchmark：文獻探索與方法推導

最後更新：`2026-08-22`

## 摘要

本文件回答的不是「要新增哪個 agent 技巧」，而是「如何建立足以支撐論文比較的 XBrainLab
agent benchmark」。研究主張預定為：在同一個已篩選 local LLM、相同 case family 與相同產品
command semantics 下，新架構相較於 2025 legacy topology 有較高的端到端 episode success，且不以
critical unsafe action 換取分數。

文獻與本地系統證據共同導出五項核心設計：

1. 以可執行 state transition 與 terminal state 為主評分，不以 tool name exact match 代替任務成功。
2. 保留 tool、argument、control-flow 等分解指標作為診斷，但不把它們宣稱成端到端成果。
3. gold test 以人工原創 semantic families 為主；合成變體只作壓力測試與語言／表達覆蓋。
4. legacy 與 current 架構只比較共同可表達的 `Common-Episode`；current-only 能力另報
   `XBrainLab-Full`，不得混入主要優越性數字。
5. benchmark 只觀測真正的 `ApplicationService / Command API`，不建立第二個產品 state machine。

這是一個研究設計凍結文件，不是結果報告。目前沒有正式模型比較、準確率或優越性結果。

## 1. 研究問題與主張邊界

### 1.1 主要研究問題

> 在控制 local model、case family、initial product state 與執行預算後，新的 XBrainLab agent
> architecture 是否比 legacy topology 更常安全地完成使用者的 EEG workflow episode？

### 1.2 次要研究問題

- 改善發生在 decision、control、execution 還是 user communication？
- 模型由約 2B 放大到約 4B 時，架構差異是否仍可重現？
- 哪些架構元件對成功與安全必要？此問題只在主比較完成後用有限 ablation 回答。
- current architecture 在 legacy 無法表達的 XBrainLab-Full workflows 上能做到什麼？這是能力描述，
  不是 legacy superiority comparison。

### 1.3 不主張的內容

- 不把 EEG classifier accuracy 當 agent accuracy。
- 不把 deterministic prerecorded replay 當 local LLM 表現。
- 不把產品 Stable 50-case gate 升格為 thesis benchmark。
- 不把 2025 raw outputs 的 250 rows 當 accuracy，因為它們沒有 frozen scorer 或 verdict。
- 不聲稱本 benchmark 能代表所有 desktop agents、所有 EEG 軟體或所有語言。

## 2. 文獻探索方法

### 2.1 範圍與日期

探索截止日為 `2026-08-22`。問題導向搜尋涵蓋：function/tool calling、stateful multi-turn agents、
executable environments、tool-task generation、synthetic benchmark quality 與 multi-turn data generation。
優先使用作者／會議官方頁面、ACL Anthology、NeurIPS／ICLR proceedings 與 arXiv 原始稿；部落格、
leaderboard 二手解讀與未能追溯方法的數字不作設計依據。

### 2.2 納入與排除準則

納入文獻須至少直接處理下列一項：tool selection／argument correctness、stateful execution、final-state
verification、multi-turn user interaction、case generation quality或 benchmark validity。純 prompt 技巧、
沒有 evaluation construction 細節的模型宣傳、與 tool-use 無關的通用 benchmark 均排除。

證據分三層使用：

- 同行審查 benchmark／method paper：可直接支持評量構面或風險。
- technical report／arXiv：只支持候選工程做法，並明標證據層級。
- XBrainLab source、Git history 與 artifacts：支持本系統的 comparator 與可觀測邊界，不外推成一般結論。

### 2.3 可重現搜尋主題

使用的主題詞包括 `function calling benchmark executable evaluation`、`stateful tool use benchmark
milestone minefield`、`multi-turn agent final database state`、`computer agent real environment benchmark`、
`tool benchmark generation verification`、`synthetic evaluation benchmark quality`。正式撰文時應保存搜尋日、
來源 URL 與納入理由；本文件的參考文獻是目前 canonical source list。

## 3. Evidence matrix

| 來源 | 經同行審查 | 與本研究直接相關的證據 | 對 XBrainLab 的限制 |
| --- | --- | --- | --- |
| BFCL / function-calling technical report | technical report | tool、argument、multi-turn function-calling 可分解診斷 | 不等同 desktop workflow terminal success |
| ToolSandbox | Findings of NAACL 2025 | stateful tool execution、implicit dependencies、milestones、minefields與 on-policy user | environment 與 XBrainLab state 不同；case authoring昂貴 |
| tau-bench | ICLR 2025 | agent、user、tool interaction與 final database state；多次試驗的一致性 | customer-service policy 不可直接當 EEG policy |
| OSWorld | NeurIPS 2024 Datasets & Benchmarks | 真實 desktop/web apps與 executable end state | 通用 GUI 操作不提供 XBrainLab domain oracle |
| TaskBench | NeurIPS 2024 Datasets & Benchmarks | tool graph、task decomposition、selection、parameter prediction及 human verification | generated cases仍需 domain expert審核 |
| APIGen | NeurIPS 2024 Datasets & Benchmarks | format、execution、semantic 三階段驗證 | API成功不一定等於有狀態 episode成功 |
| ToolLLM / ToolBench | ICLR 2024 | 大規模自動指令與 tool trajectory 生成的可行性 | 規模不能替代 gold quality與可解性 |
| Quality Matters | EMNLP 2024 | tool-use synthetic data需系統性 correctness 檢查；較少但高品質資料可能更有效 | 研究結果針對其抽樣資料，不可泛化成所有 synthetic data |
| What Has Been Lost with Synthetic Evaluation? | Findings of EMNLP 2025 | 在兩個 reading-comprehension case studies中，合成 benchmark雖常有效但較容易 | 不是 tool-use實驗；只支持保守使用 synthetic gold |
| APIGen-MT | NeurIPS 2025 Datasets & Benchmarks | task blueprint、ground-truth actions、review committee、simulated human-agent multi-turn trajectory | simulated human仍可能引入行為偏差 |
| ToolACE | arXiv 2024 | multi-agent generation與規則／模型驗證可作候選資料管線 | 非同行審查；不能作 sealed human test替代品 |

上述文獻沒有共同提出本文件的五個 macro strata、Common-Episode 或 XBrainLab-Full；這些是把既有
evaluation principles 與 XBrainLab command spine、legacy surface和 EEG workflow結合後的研究推論。

## 4. XBrainLab 與 legacy archaeology

### 4.1 Current system boundary

目前產品 command spine 是 `ApplicationService / Command API`。Assistant 可提出 tool call，但 admission、
confirmation、authoritative mutation、publication與 error semantics仍由 backend owner決定。Benchmark
因此只能記錄 public `ApplicationViewPublication`、verified call與 `CommandResult`；若 benchmark自己
推演一套 app state，評到的是 mock而不是產品。

目前 18-action surface與產品 Stable runner可用來理解 current contract及做工程回歸，但 Stable runner
的 case目的、scorer與證據層級不同，不能直接成為論文 gold。

### 4.2 Legacy comparator

Legacy code、prompt與 raw outputs固定在 commit
`94adb570f8eb660b771096748b8431f01f8935d7`。復現契約保存：

- 六個 router prompts及原 command語意。
- RAG character chunk size `512`、top `3`、相似度 admission為 mean + std 且至少 `0.2`。
- 每題生成 `1` 或 `3` samples；temperature `0.6`、top-p `0.9`；多 sample依 command sequence投票。
- 只使用最新 user turn；後續歷史對話改動不回填到 baseline。
- Python `3.9.20`、torch `2.5.0`、transformers `4.46.0`、sentence-transformers `3.2.1` 等已知環境釘選。

遺漏的原始 RAG corpus可追溯到 CECNL `AI-agent` branch commit
`b07f500ee3f6e7180db309447432c01230f1957f` 的
`remote/txt_output/formatted_output.txt`，Git blob SHA
`555cc5612e8d2154fecbc1c6c1dba1a973fc27f2`，大小 `45,277` bytes。未完成來源／授權審核前，repo
只應保存來源、hash與 fetch recipe，不重散布 corpus。

原 Gemma model revision未釘選，因此 native replay最多標為 approximate reproduction。安全 adapter可用
strict parser取代 Python `eval`，也可移除 Flask／UI automation／unbounded retry，但不得加上 current
verification、repair、default route或 state guard來救 legacy輸出；否則比較對象已變。

### 4.3 Comparator alignment

兩套 surface不同，不能用 literal tool-name equality作主比較。每個 gold family先定義與實作無關的
semantic goal、initial state、milestones、minefields、required communication與 terminal predicates，
再為 legacy/current各自提供 action mapping。只有雙方確實可表達的 families進入 Common-Episode。
無法映射者進 XBrainLab-Full，並清楚標為 current-only。

## 5. 從替代方案推導最終設計

| 設計問題 | 候選方案 | 排除或限制理由 | 凍結決策 |
| --- | --- | --- | --- |
| 主評分單位 | 單次 tool call、turn、episode | tool call正確不保證流程完成；turn會忽略延遲 effect | semantic-family clustered episode success |
| success oracle | exact call、LLM judge、state predicates | exact call懲罰等價路徑；LLM judge不可完全重算 | terminal + required milestones + zero minefields + communication + budget 的 deterministic conjunction |
| 執行環境 | 全 mock、全 GUI、hybrid | mock失真；全 GUI成本與非決定性過高 | 真 ApplicationService為主，代表性 Qt subset補可見性 |
| gold來源 | 全 synthetic、全人工、hybrid | synthetic可擴展但可能偏易；全人工難覆蓋壓力變體 | sealed human-original primary + synthetic/agent stress secondary |
| 比較 surface | literal legacy tools、current全部工具、semantic common scope | literal不公平；current-only混入會灌高新架構 | Common-Episode primary + XBrainLab-Full separate |
| 語言 | 只中文、只英文、雙語各算N | 單語限制外部效度；paired variants不是獨立樣本 | 每 family zh-TW/English配對且同 partition，不增加N |
| 樣本數 | 固定50、固定100、pilot/power | 任意 row count忽略 cluster與effect uncertainty | pilot估 paired family變異後凍結N |
| 安全性 | 併入平均分、獨立 gate | 平均分可用大量easy cases稀釋critical failure | new 2B sealed matrix需 zero critical minefield |
| 架構搜尋 | 不限次手調、預註冊有上限 | 不限次會對development過擬合 | 最多8個registered variants、最多3個進validation |

## 6. 最終 benchmark 方法

### 6.1 兩個 scope

- `Common-Episode`：legacy與current都可達成的共同 semantic goals；同一 selected model下的主比較。
- `XBrainLab-Full`：current product的完整 capability與 safety coverage；只報絕對表現與 failure profile。

### 6.2 四個 family-disjoint partitions

`model_selection`、`architecture_development`、`architecture_validation`、`sealed_human_test` 必須以
semantic family分割。翻譯、paraphrase、fixture variant與repeat跟隨 parent family，不可跨 split。
model選擇只看第一區；架構選擇只看 development；停止選擇後才可依序開 validation及 sealed test。

### 6.3 五個等權 macro strata

1. acquisition / orientation
2. direct preprocessing
3. pipeline configuration
4. execution / result / navigation
5. clarification / refusal / recovery

Macro Episode score先在 family內聚合，再在 stratum內聚合，最後五個 strata等權平均，避免大量
happy-path rows掩蓋稀少但重要的 refusal/recovery。

### 6.4 Case construction與審核

每個 family由 human author從產品 workflow、domain risk與 legacy/current共同語意撰寫；agent只可提出
challenge候選。每個 case須有 provenance、rationale、initial state、allowed variants、可執行 oracle與
minefields。單一 reviewer完整審核後，至少隔 `14` 天做 blind re-review；最多抽 `20%` cases或
`30` families（取較先達限制者）。只有同一人審核，因此只能報 intra-rater agreement，不稱 inter-rater。

### 6.5 Environment與資料來源

主矩陣以真正 ApplicationService及 deterministic scripted GUI-owned user執行；必要的確認、補參數與取消
回應由 case script提供，不由 benchmark偷改 state。代表性 subset再經 Qt確認可見結果。資料 robustness
規劃至少涵蓋四種 source family：A01T GDF + MAT、EEGMMIDB `S008R04` EDF、BBCI O3VR GDF，以及
MNE-BIDS tiny／OpenNeuro `ds003061` P300。實際納入前逐一凍結license、checksum、slice與cleanup。

### 6.6 Model control

先在中立 `model_selection` families篩 2B與4B候選。所有候選使用相同可用 context `8192`、max output
`512`、BF16、greedy decoding與相同 logical schema；任何模型因官方格式需要的薄 adapter須公開。
2B候選：Granite 3.3 2B、Gemma 2 2B、SmolLM2 1.7B。4B候選：Phi-4-mini 3.8B、Gemma 3 4B、
Llama 3.2 3B。下載前仍須依 repo policy審核來源、license、revision、VRAM、大小與cache。

主要比較使用選出的同一 2B model；4B是 replication，不與2B合併。Legacy原模型只作 native approximate
reproduction背景，不是公平主比較。

### 6.7 重複、統計與成功規則

development pilot每個 configuration先做 `R=5` repeats，估計 family-level paired difference、
intraclass dependence與 repeat Monte Carlo standard error。正式矩陣預設 `R=3`；若 pilot顯示主要 macro
Episode estimate的 repeat MC SE超過 `1` percentage point，預註冊提升為 `R=5`。

正式 N不由 row數決定。以 semantic family為抽樣單位，使用 pilot effect／variance做 paired clustered
power analysis；凍結後不得因 test結果補 cases。主要 uncertainty使用至少 `10,000` draws的 hierarchical
paired bootstrap：先依 stratum重抽 family，再保留 family內配對的 architecture、語言、fixture與repeat。

預註冊成功需同時滿足：

- 2B Common-Episode 五-stratum macro improvement至少 `+10` percentage points；
- paired hierarchical bootstrap 95% CI下界 `> 0`；
- new 2B sealed matrix `0` 個 critical minefield；
- 沒有 schema、split、environment或artifact integrity failure。

Decision score、XBrainLab-Full、4B replication、latency/token與各 failure taxonomy均為 secondary，不得在
primary rule失敗時替換主張。

## 7. 架構迭代與 ablation 控制

本 benchmark建立後才進架構研究。最多登記8個 architecture variants；development依 safety gate、macro
Episode、latency與complexity選擇，最多3個進 architecture_validation。若已有top 3，且連續兩個明確
hypothesis都未提升至少2 percentage points，停止探索。近似平手時採 one-standard-error原則，選較簡單／
便宜者。開 sealed test後不再改 prompt、tools、parser、retry、case或 scorer。

最後架構凍結後最多做4個理論對應 ablations。Ablation只回答元件貢獻，不重新挑冠軍，也不能用 sealed
test調整元件。

## 8. Sealing、artifact與可重算性

Human validation/test bundle使用不同 GPG keys加密；keys存 repo外。Repo只保留 encrypted bundle、SHA-256、
schema/version與一次性 access ledger。這是 researcher-controlled self-sealing，不宣稱第三方託管或真正
blind custody。

每個 run保存 immutable run manifest、case hashes、model revision、architecture ID、environment、normalized
trace、verdict與 scorer version。Episode、Decision、Control、Execution四層分開；每個數字必須能由 frozen
case與 normalized trace離線重算。Incomplete、unknown predicate、hash mismatch或 missing trace一律 fail closed。
可重算不代表可無條件公開：shareable projection移除local paths、private subject/patient metadata、diagnostics、
prompts/tokens與未審核transcript；正式matrix只使用已審核的public或checked-in EEG sources。

## 9. Threats to validity

- **Construct validity**：state predicates可能漏掉使用者實際感受；以人工 case review與Qt subset緩解。
- **Internal validity**：adapter或不同 tool surface可能偏袒一方；以 semantic oracle、同模型與公開 mapping緩解。
- **Selection bias**：單一 researcher author/reviewer有偏差；延遲盲審只能提供 intra-rater證據，論文須揭露。
- **Contamination**：公開 development cases可能被調參；family-disjoint encrypted validation/test緩解。
- **Stochasticity**：小模型輸出有變異；paired repeats、MC SE gate與 hierarchical bootstrap緩解。
- **External validity**：四個資料 source與雙語仍不能代表所有 EEG資料或使用者。
- **Reproduction**：legacy model revision缺失，使 native legacy replay只能 approximate；公平主比較改用同一 selected model。
- **Synthetic bias**：agent stress cases可偏易或帶有模型風格，因此不混入 human sealed primary。
- **Privacy／deployment boundary**：trace、diagnostics與metadata可能帶出local path或subject identity；shareable
  projection預設redact且正式matrix只用審核過的public/checked-in data。本protocol只涵蓋local single-user
  research，不支撐remote、multi-user、clinical或regulated deployment claim。

## 10. 參考文獻

- Yan, F. (2025). [A Function Calling Perspective on Scalable Large Language Model Agent Evaluation](https://www2.eecs.berkeley.edu/Pubs/TechRpts/2025/EECS-2025-184.html). UC Berkeley Technical Report.
- Lu et al. (2025). [ToolSandbox: A Stateful, Conversational, Interactive Evaluation Benchmark for LLM Tool Use Capabilities](https://aclanthology.org/2025.findings-naacl.65/). Findings of NAACL 2025.
- Yao et al. (2025). [τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains](https://proceedings.iclr.cc/paper_files/paper/2025/hash/1b126cc38b8638e07bef37e7b2bb72bf-Abstract-Conference.html). ICLR 2025.
- Xie et al. (2024). [OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks in Real Computer Environments](https://papers.nips.cc/paper_files/paper/2024/hash/5d413e48f84dc61244b6be550f1cd8f5-Abstract-Datasets_and_Benchmarks_Track.html). NeurIPS 2024 Datasets and Benchmarks.
- Shen et al. (2024). [TaskBench: Benchmarking Large Language Models for Task Automation](https://proceedings.neurips.cc/paper_files/paper/2024/hash/085185ea97db31ae6dcac7497616fd3e-Abstract-Datasets_and_Benchmarks_Track.html). NeurIPS 2024 Datasets and Benchmarks.
- Liu et al. (2024). [APIGen: Automated Pipeline for Generating Verifiable and Diverse Function-Calling Datasets](https://proceedings.neurips.cc/paper_files/paper/2024/hash/61cce86d180b1184949e58939c4f983d-Abstract-Datasets_and_Benchmarks_Track.html). NeurIPS 2024 Datasets and Benchmarks.
- Qin et al. (2024). [ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs](https://proceedings.iclr.cc/paper_files/paper/2024/hash/28e50ee5b72e90b50e7196fde8ea260e-Abstract-Conference.html). ICLR 2024.
- Iskander et al. (2024). [Quality Matters: Evaluating Synthetic Data for Tool-Using LLMs](https://aclanthology.org/2024.emnlp-main.285/). EMNLP 2024.
- Gill et al. (2025). [What Has Been Lost with Synthetic Evaluation?](https://aclanthology.org/2025.findings-emnlp.526/). Findings of EMNLP 2025.
- Prabhakar et al. (2025). [APIGen-MT: Agentic Pipeline for Multi-Turn Data Generation via Simulated Agent-Human Interplay](https://proceedings.neurips.cc/paper_files/paper/2025/hash/5e3661f7fe4c8ac5652d62eb3d3c96ea-Abstract-Datasets_and_Benchmarks_Track.html). NeurIPS 2025 Datasets and Benchmarks.
- Liu et al. (2024). [ToolACE: Winning the Points of LLM Function Calling](https://arxiv.org/abs/2409.00920). arXiv preprint.
