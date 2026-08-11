# XBrainLab 專案控制室

最後更新：`2026-08-11`

XBrainLab 是本地優先的 EEG / BCI 桌面分析工具。目前可執行的 Desktop GUI checkpoint 已
收斂到 `main`；這個入口用來快速判斷現況、缺口和證據。

!!! warning "目前邊界"
    真人資料手測目前只支撐 Graz 2a GDF 與 OpenNeuro ds003061 P300 BIDS 各一個資料集。
    Assistant 尚未準備好，效能與舊 Agent gate 仍需重整；這不是 release 或 product complete。

!!! danger "仍未完成"
    Assistant 互動與真實 Granite 2B 行為、舊 Agent gate 校準，以及 load / refresh / preprocess /
    plotting / training 效能仍是 active work。`main` 只代表開發基線已收斂，不代表這些區域完成。

<div class="xlb-signal-list" markdown>

<div markdown>
<span class="xlb-kicker">Product Status</span>
Main development checkpoint; not release-ready.
</div>

<div markdown>
<span class="xlb-kicker">主要缺口</span>
Assistant prototype、Agent gates、performance polish 和更廣泛真人資料驗收。
</div>

<div markdown>
<span class="xlb-kicker">Data Import</span>
One Graz GDF family and one OpenNeuro P300 BIDS dataset manually exercised.
</div>

<div markdown>
<span class="xlb-kicker">證據邊界</span>
Final totals 只讀 clean exact-commit handoff evidence，不從舊 notes 手動加總。
</div>

<div markdown>
<span class="xlb-kicker">Artifacts</span>
local quality dashboard；screenshot index；private docs portal visual review.
</div>

<div markdown>
<span class="xlb-kicker">Next Work</span>
Teacher-facing GUI/data fixes, measured performance work, then simplified Assistant prototype.
</div>

</div>

## Review Board

| Area | Current Read | Best Evidence | Next Work |
| --- | --- | --- | --- |
| Product readiness | `main` is the accepted development checkpoint, not a release or completed product. | [Current](current.md), [Now](planning/now.md) | Stabilize teacher-facing GUI/data use, then performance and Assistant. |
| Backend architecture | `ApplicationService / Command API` is the shared backend spine; `BackendFacade` and product live-object result payloads are physically removed. | [Architecture](architecture/README.md), [Historical Audit](records/product_quality_audit_2026-07-30.md) | Preserve these boundaries while addressing measured product issues; keep P2 cleanup separate. |
| Data Import | `scan -> preview -> validate -> apply -> recipe` is a bounded baseline. Manual acceptance currently covers one Graz GDF family and one OpenNeuro P300 BIDS dataset. | [Data Interpretation target](target/data_interpretation_system.md), [Validation](validation/README.md) | Add dataset-by-dataset acceptance without turning format coverage into broad support claims. |
| Validation | Historical dashboards and old Agent gates are not current product verdicts. | [Validation](validation/README.md); generated `artifacts/quality/latest.md` header | Recalibrate Agent gates and build the next candidate evidence from one explicit commit. |

## Evidence Shortcuts

<div class="grid cards xlb-artifact-grid" markdown>

- **Quality dashboard**

    Mutable local report. The `ux/assistant-product-v1@3869aaef` copy is baseline-only; closure
    evidence requires a clean exact-commit `handoff` profile.

    <span class="xlb-artifact-path">`artifacts/quality/latest.md` (inspect identity before use)</span>

- **Data Import screenshots**

    Dirty-tree checkpoint; useful for review only after reading its manifest identity.

    <span class="xlb-artifact-path">`artifacts/ui/data-import-wizard-steps/` (checkpoint only)</span>

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

    看老師試用前 GUI/data stabilization、效能打磨、Assistant prototype 與 gate 重整順序。

    [打開 Now](planning/now.md)

- **Roadmap**

    看 Rebaseline、Desktop MVP、Product Polish / Release Candidate、Assistant MVP、Thesis Evidence 的階段安排。

    [打開 Roadmap](planning/roadmap.md)

- **Target architecture**

    看理想狀態：UI、assistant、scripts 共用 Application Service / Command API。

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
| `artifacts/quality/latest.md` | 只有當 header 顯示 current branch、能唯一對應 full pushed SHA 的 commit、handoff profile 和允許的 clean/protected-local state 時，才支撐該 commit 的工程 gate。 | Canonical current truth、其他 branch、product completion、human Windows acceptance、thesis claim。 |
| `artifacts/agent_evals/dashboard.md` | Historical / exploratory tool-call benchmark slice；只有產品 closure 後 freeze 的 exact-source suite 才能成為 thesis evidence。 | Current product readiness、EEG training accuracy、UI usability、product completion。 |
| `artifacts/data_interpretation/format-capability-matrix.md` | Representative Data Interpretation scan/preview/validation format boundaries。 | Full manual certification for every real dataset or XDF / LSL parser support。 |
| `artifacts/ui/data-import-wizard-steps/` | Dirty tracked checkpoint；supports review of captured states only after reading its evidence JSON。 | Current candidate evidence、final Match Labels / Review and Import UX approval、clean exact-commit handoff。 |
| `artifacts/launcher/windows-launcher-walkthrough.md` | Automated Windows launcher command/startup smoke。 | Human click-through release approval。 |

Artifact governance lives in `artifacts/README.md`; artifacts are evidence outputs, not canonical
truth. Current tree is intentionally pruned: short historical slices and duplicated screenshots
belong in git history unless they are still needed for current evidence. Current truth belongs in
[current.md](current.md), architecture docs, and validation docs.

## 長期產品主線

1. Rebaseline。
2. Desktop MVP。
3. Product Polish / Release Candidate。
4. Assistant MVP。
5. Thesis Evidence。

## 網站地圖

| 區域 | 用途 |
| --- | --- |
| [專案現況](current.md) | current truth、claim boundary、操作入口。 |
| [產品計畫](planning/now.md) | immediate work vs roadmap。 |
| [產品回饋](records/product_feedback.md) | 人工使用時的 UI / UX 觀察、困惑點、未來設計方向。 |
| [目標](target/README.md) | 需求、目標架構、agent / Data Interpretation 終局設計。 |
| [目前架構](architecture/README.md) | 目前 implementation、backend command spine、active risks。 |
| [驗證](validation/README.md) | evidence tiers、artifact interpretation、validation gates。 |
| [Historical Audit](records/product_quality_audit_2026-07-30.md) | 已完成 closure 的 provenance；不是 active queue。 |
| [決策](decisions/README.md) | active product/architecture decisions；不是 worklog。 |
