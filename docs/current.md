# XBrainLab Current Truth

最後更新：`2026-05-09`

This page is the short operational truth. It intentionally omits slice-by-slice history so the
documentation site stays readable as a project control room.

## Status Snapshot

| Topic | Current state | Boundary |
| --- | --- | --- |
| Product phase | Product-delivery engineering. The app has a stronger backend command spine and usable automated UI evidence. | Not product-complete. |
| Backend core | `ApplicationService / Command API` is the shared route for UI, agent, headless scripts, and MCP. Several workflow services have been split out of the former god-object path. | Architecture is improved but not fully clean; UI refresh and controller fallback audit remain active risks. |
| UI / assistant | ChatPanel and Data Interpretation wizard have product-oriented polish and automated walkthrough coverage. | Automated replay is not human Windows desktop acceptance. |
| Data Interpretation | Scan -> preview -> validate -> confirm/apply -> save/reload recipe baseline exists, including metadata, class map, event roles, label carrier choices, and format capability boundaries. | Not a final import system; embedded label editor, raw trigger selector, complex anchor reconciliation, XDF / LSL parser, and mature recipe diff UX remain missing. |
| Local LLM runtime | Product path is local-only. Primary/fallback model choices and tool-call benchmark artifacts exist. | Long real local-model desktop soak and full release refresh for the expanded source suite are not complete. |
| Packaging | Windows launcher command/startup smoke exists for the active repo. | Not human click-through release approval. |

## Most Important Blockers

1. Documentation reset: the source truth exists, but the reader path must stay short and evidence-aware.
2. Architecture health: command spine cleanup, UI refresh coordination, and controller fallback audit are not finished.
3. Human desktop acceptance: Windows launcher, DPI, dual-monitor, and long local-model sessions still need human verification.
4. Data Interpretation maturity: the wizard is a strong baseline, not the final import/label review system.
5. Release/thesis evidence discipline: tool-call eval should be refreshed only when a formal benchmark claim changes.

## What Can Be Claimed

| Claim | Current support |
| --- | --- |
| Fast engineering health has a clean recent dashboard. | `artifacts/quality/latest.md` reports PASS for the fast profile. |
| The main UI workflow has automated PyQt replay evidence. | `artifacts/ui/human-like-walkthrough/human-like-walkthrough.md` reports `26 / 26` phases and `20` screenshots. |
| Data Interpretation exposes representative format boundaries. | `artifacts/data_interpretation/format-capability-matrix.md` is generated from live `ApplicationService` commands. |
| MCP has stdio / HTTP baseline evidence. | `artifacts/mcp/stdio-walkthrough.md` and `artifacts/mcp/http-walkthrough.md` cover headless command paths. |
| Tool-call benchmark slice has local primary/fallback evidence. | `artifacts/agent_evals/dashboard.md` summarizes deterministic and local model runs for the prior formal slice. |

## What Must Not Be Claimed

- Product complete.
- Data Interpretation final import system.
- Backend target architecture fully aligned.
- Automated UI replay equals human Windows desktop acceptance.
- Tool-call eval score equals UI/product completion.
- Local runtime smoke equals long desktop local-model acceptance.

## Next Work

See [planning/now.md](planning/now.md) for the active queue. The priority order is:

1. Finish documentation reset.
2. Resume architecture health baseline work.
3. Continue Data Interpretation mature wizard slices.
4. Extend UI / assistant product walkthrough toward human Windows acceptance.
5. Run release/thesis gates only when updating formal claims.

## Canonical Entrypoints

| Need | Read |
| --- | --- |
| Product tracks and future work | [planning/roadmap.md](planning/roadmap.md) |
| Immediate work queue | [planning/now.md](planning/now.md) |
| Evidence tiers and gates | [validation/README.md](validation/README.md) |
| Current architecture | [architecture/README.md](architecture/README.md) |
| Artifact governance | `artifacts/README.md` |
