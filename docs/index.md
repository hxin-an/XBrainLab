# XBrainLab Project Control Room

XBrainLab is a local-first EEG / BCI desktop analysis tool under product-delivery engineering.
This site is the current project portal: it should let a reader understand status, blockers,
evidence, and next work without digging through raw logs first.

!!! warning "Current boundary"
    XBrainLab is not product-complete. Automated UI walkthroughs, dashboard PASS results, MCP
    walkthroughs, and tool-call evals are useful evidence, but they do not replace human Windows
    desktop acceptance or long local-model desktop sessions.

<div class="xlb-status-panel" markdown>

<div class="xlb-evidence-strip" markdown>

<div markdown>
<span class="xlb-kicker">Product Phase</span>
Product-delivery engineering. Keep reducing split truth before adding broad new features.
</div>

<div markdown>
<span class="xlb-kicker">Main Blocker</span>
Docs and architecture evidence are ahead of the readable site entrypoint.
</div>

<div markdown>
<span class="xlb-kicker">UI Evidence</span>
Automated PyQt walkthrough passed. Human Windows launcher / DPI acceptance remains open.
</div>

<div markdown>
<span class="xlb-kicker">Agent Evidence</span>
Formal `121` case local benchmark slice exists. It is not a product-completion claim.
</div>

</div>

</div>

## Start Here

<div class="grid cards" markdown>

- **Current Truth**

    Read the short state of the project, blockers, claim boundaries, and next work.

    [Open current.md](current.md)

- **Product Plan**

    See the product tracks, completion criteria, and future work that is not a current blocker.

    [Open roadmap](planning/roadmap.md)

- **Validation**

    Understand evidence levels before using any artifact as proof.

    [Open validation](validation/README.md)

- **Architecture**

    Trace how UI, assistant, MCP, and scripts should share the backend command spine.

    [Open architecture](architecture/README.md)

</div>

## Evidence Board

| Evidence entry | Supports | Does not support |
| --- | --- | --- |
| `artifacts/quality/latest.md` | Fast engineering health: lint, type, architecture guard, startup smoke, UI baseline, real-data IO. | Product completion, thesis claim, local LLM readiness. |
| `artifacts/ui/human-like-walkthrough/human-like-walkthrough.md` | Automated PyQt replay with screenshots, visible text, button states, geometry checks. | Human Windows desktop acceptance, DPI / dual-monitor confidence, long local-model session. |
| `artifacts/agent_evals/dashboard.md` | Tool-call benchmark slice for selected local models and deterministic baseline. | EEG training accuracy, UI usability, product completion. |
| `artifacts/mcp/http-walkthrough.md` | Headless MCP HTTP transport, tools/list, scan/preview, train job status/cancel baseline. | Full MCP client certification, UI refresh, persistent recovery. |
| `artifacts/data_interpretation/format-capability-matrix.md` | Representative Data Interpretation scan/preview/validation format boundaries. | Full manual certification for every real dataset or XDF / LSL parser support. |
| `artifacts/launcher/windows-launcher-walkthrough.md` | Automated Windows launcher command/startup smoke. | Human click-through release approval. |

Artifact governance lives in `artifacts/README.md`; artifacts are evidence outputs, not canonical
truth. Current truth belongs in `docs/current.md` and architecture / validation docs.

## Current Work Queue

1. Documentation reset: make `current.md`, roadmap, validation, and artifact governance readable.
2. Architecture health: continue command spine cleanup, refresh coordination, and controller fallback audit.
3. Data Interpretation maturity: improve label/event review, recipe reload/diff, and format boundaries.
4. UI / assistant walkthrough: keep screenshot evidence, then add human Windows desktop acceptance.
5. Release / thesis gates: refresh full local eval only when a formal claim is being updated.

## Site Map

| Section | Use it for |
| --- | --- |
| [Core](current.md) | Current truth and operations. |
| [Product Plan](planning/now.md) | Now/roadmap split: immediate work versus product tracks. |
| [Architecture](architecture/README.md) | Current implementation boundaries and command spine. |
| [Validation](validation/README.md) | Evidence tiers, artifact interpretation, gates. |
| [Operations](operations.md) | Local build, deployment, and runtime commands. |
