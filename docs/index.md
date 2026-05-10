# XBrainLab 專案控制室

XBrainLab 是本地優先的 EEG / BCI 桌面分析工具，目前正在產品化整理中。
這個網站是專案入口：用來快速看懂目前狀態、下一步、架構邊界和證據，不用先翻流水帳。

!!! warning "目前邊界"
    XBrainLab 還不能宣稱 product complete。CI 綠燈、automated UI walkthrough、MCP
    walkthrough、tool-call eval 都是有用證據，但不能取代 human Windows desktop acceptance、
    長時間 local-model desktop session，或正式 release approval。

<div class="xlb-status-panel" markdown>

<div class="xlb-evidence-strip" markdown>

<div markdown>
<span class="xlb-kicker">目前階段</span>
Windows Desktop MVP baseline：backend、Data Interpretation、tool-call、desktop acceptance。
</div>

<div markdown>
<span class="xlb-kicker">主要缺口</span>
Phase 1A 要清掉 product legacy path，收斂 UI page refresh，並同步清理測試。
</div>

<div markdown>
<span class="xlb-kicker">目標 vs 現況</span>
`target/` 是目標態；`architecture/` 是目前實作和風險。
</div>

<div markdown>
<span class="xlb-kicker">證據邊界</span>
artifact 是 evidence，不是 current truth；claim 要回到 Current / Validation 判讀。
</div>

</div>

</div>

## 先看這裡

<div class="grid cards" markdown>

- **目前真相**

    看現在能 claim 什麼、不能 claim 什麼，以及 roadmap 是否和 source code 對齊。

    [打開 Current](current.md)

- **下一步**

    看下一輪施工焦點：Backend Command Spine / Legacy / Test / UI Refresh Cleanup。

    [打開 Now](planning/now.md)

- **Roadmap**

    看 MVP baseline、Release Candidate、Thesis / Agent Evidence、MCP hardening 的階段安排。

    [打開 Roadmap](planning/roadmap.md)

- **目標架構**

    看理想狀態：UI、agent、MCP、scripts 共用 Application Service / Command API。

    [打開目標架構](target/architecture.md)

- **目前架構**

    看目前 source code 實際狀態、已落地的 command spine，以及仍存在的架構風險。

    [打開目前架構](architecture/README.md)

- **驗證策略**

    看測試和 artifact 能支撐什麼 claim，哪些不能被過度解讀。

    [打開驗證策略](validation/README.md)

</div>

## 目標與現況怎麼分

| 區域 | 用途 | 讀法 |
| --- | --- | --- |
| `docs/target/` | 目標態、需求、理想架構、agent 目標。 | 這是方向，不代表目前已完成。 |
| `docs/architecture/` | 目前實作架構、source code 邊界、active risks。 | 這是 current implementation read。 |
| `docs/planning/` | 接下來怎麼做。 | `now.md` 是短期，`roadmap.md` 是產品主線。 |
| `docs/validation/` | evidence 等級和 claim boundary。 | 用來判斷 artifact / tests 能證明什麼。 |
| `artifacts/` | 機器產生的證據輸出。 | evidence，不是 canonical truth。 |

## 證據板

| 證據入口 | 能支撐 | 不能支撐 |
| --- | --- | --- |
| `artifacts/quality/latest.md` | Fast engineering health：lint、type、architecture guard、startup smoke、UI baseline、real-data IO。 | Product completion、thesis claim、local LLM readiness。 |
| `artifacts/ui/human-like-walkthrough/human-like-walkthrough.md` | Automated PyQt replay with screenshots、visible text、button states、geometry checks。 | Human Windows desktop acceptance、DPI / dual-monitor confidence、long local-model session。 |
| `artifacts/agent_evals/dashboard.md` | Tool-call benchmark slice for selected local models and deterministic baseline。 | EEG training accuracy、UI usability、product completion。 |
| `artifacts/mcp/http-walkthrough.md` | Headless MCP HTTP transport、tools/list、scan/preview、train job status/cancel baseline。 | Full MCP client certification、desktop UI refresh、persistent recovery。 |
| `artifacts/data_interpretation/format-capability-matrix.md` | Representative Data Interpretation scan/preview/validation format boundaries。 | Full manual certification for every real dataset or XDF / LSL parser support。 |
| `artifacts/launcher/windows-launcher-walkthrough.md` | Automated Windows launcher command/startup smoke。 | Human click-through release approval。 |

Artifact governance lives in `artifacts/README.md`; artifacts are evidence outputs, not canonical
truth. Current truth belongs in [current.md](current.md), architecture docs, and validation docs.

## 目前工作主線

1. Phase 1A：Backend Command Spine / Legacy / Test / UI Refresh Cleanup。
2. Phase 1B：Data Interpretation MVP Slice。
3. Phase 1C：Tool-Call Product Baseline。
4. Phase 1D：Windows Desktop MVP Acceptance。
5. Phase 2：Release Candidate Hardening。
6. Phase 3：Thesis / Formal Agent Evidence。
7. Phase 4：MCP / External Agent Hardening。

## 網站地圖

| 區域 | 用途 |
| --- | --- |
| [專案現況](current.md) | current truth、claim boundary、操作入口。 |
| [產品計畫](planning/now.md) | immediate work vs roadmap。 |
| [產品回饋](records/product_feedback.md) | 人工使用時的 UI / UX 觀察、困惑點、未來設計方向。 |
| [目標](target/README.md) | 需求、目標架構、agent / Data Interpretation 終局設計。 |
| [目前架構](architecture/README.md) | 目前 implementation、backend command spine、active risks。 |
| [驗證](validation/README.md) | evidence tiers、artifact interpretation、validation gates。 |
