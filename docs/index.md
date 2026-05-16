# XBrainLab 專案控制室

XBrainLab 是本地優先的 EEG / BCI 桌面分析工具，目前正在做 MVP 穩定化；下一步是 private docs review 與 human Windows smoke。這個私有入口用來快速判斷現況、缺口和證據。

!!! warning "目前邊界"
    Not product complete；automated evidence 不能取代 human Windows acceptance。

<div class="xlb-signal-list" markdown>

<div markdown>
<span class="xlb-kicker">Product Status</span>
MVP stabilization；not product complete.
</div>

<div markdown>
<span class="xlb-kicker">主要缺口</span>
Phase 1A 剩下的是 zero-controller UI 距離、human desktop acceptance、以及測試證據邊界；Windows acceptance 仍 pending。
</div>

<div markdown>
<span class="xlb-kicker">Data Import</span>
Wizard + 4 placement modes; not final UX.
</div>

<div markdown>
<span class="xlb-kicker">證據邊界</span>
artifact 和 product-success tests 是 evidence，不是第二套 truth；claim 要回到 Current / Validation 判讀。
</div>

<div markdown>
<span class="xlb-kicker">Artifacts</span>
`quality/latest.md`; screenshot index；private docs portal visual review.
</div>

<div markdown>
<span class="xlb-kicker">Next Work</span>
Private docs review; human smoke; manual-test branch review before any `main` promotion.
</div>

</div>

## Review Board

| Area | Current Read | Best Evidence | Next Work |
| --- | --- | --- | --- |
| Product readiness | Baseline exists; not product complete. | [Current](current.md), [Roadmap](planning/roadmap.md) | Human-observable desktop smoke. |
| Backend architecture | `ApplicationService / Command API` is the shared backend spine; `BackendFacade` is physically removed. | [Architecture](architecture/README.md), [Validation](validation/README.md) | Keep guards green while UX continues. |
| Data Import | `scan -> preview -> validate -> apply -> recipe` works as baseline; placement evidence covers four mainstream modes. | [Data Interpretation target](target/data_interpretation_system.md), `artifacts/ui/data-import-wizard-steps/README.md` | Record UX debt; do not redesign tonight. |
| Validation | Architecture, backend, agent/MCP, UI refresh, split regression, docs, and dashboard gates are green for current branch. | `artifacts/quality/latest.md`, [Validation](validation/README.md) | Add human Windows acceptance evidence. |

## Evidence Shortcuts

<div class="grid cards xlb-artifact-grid" markdown>

- **Quality dashboard**

    Latest fast health gate: lint, type, architecture, startup, UI baseline, UI unit suite, real-data IO.

    <span class="xlb-artifact-path">`artifacts/quality/latest.md`</span>

- **Data Import screenshots**

    Current wizard steps and Match Labels placement mode review images.

    <span class="xlb-artifact-path">`artifacts/ui/data-import-wizard-steps/README.md`</span>

- **Human-like walkthrough**

    Automated PyQt replay with screenshots and visible-state snapshots.

    <span class="xlb-artifact-path">`artifacts/ui/human-like-walkthrough/human-like-walkthrough.md`</span>

- **Internal event evidence**

    Backend generated event-evidence preview for A01T/A02T/A03T.

    <span class="xlb-artifact-path">`artifacts/data_interpretation/internal-event-preview-backend.png`</span>

</div>

## Primary Paths

<div class="grid cards" markdown>

- **Current truth**

    看現在能 claim 什麼、不能 claim 什麼，以及 roadmap 是否和 source code 對齊。

    [打開 Current](current.md)

- **Next work**

    看下一輪施工焦點：剩餘 UI controller 例外、product smoke、human acceptance。

    [打開 Now](planning/now.md)

- **Roadmap**

    看 MVP baseline、Release Candidate、Thesis / Agent Evidence、MCP hardening 的階段安排。

    [打開 Roadmap](planning/roadmap.md)

- **Target architecture**

    看理想狀態：UI、agent、MCP、scripts 共用 Application Service / Command API。

    [打開目標架構](target/architecture.md)

- **Current architecture**

    看目前 source code 實際狀態、已落地的 command spine、controller 例外分類，以及仍存在的架構風險。

    [打開目前架構](architecture/README.md)

- **Validation strategy**

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
| `artifacts/ui/data-import-wizard-steps/README.md` | Current Data Import wizard screenshots, including the four loaded-label placement mode panels。 | Final Match Labels / Review and Import UX approval。 |
| `artifacts/launcher/windows-launcher-walkthrough.md` | Automated Windows launcher command/startup smoke。 | Human click-through release approval。 |

Artifact governance lives in `artifacts/README.md`; artifacts are evidence outputs, not canonical
truth. Current tree is intentionally pruned: short historical slices and duplicated screenshots
belong in git history unless they are still needed for current evidence. Current truth belongs in
[current.md](current.md), architecture docs, and validation docs.

## 目前工作主線

1. Phase 1A：Backend Command Spine / UI Refresh / Test Evidence 收尾。
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
