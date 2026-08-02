# XBrainLab UI Reference Baselines

This directory stores approved UI reference artifacts.

Use it for curated "known-good" screenshots that UI regression checks compare against.

Keep this separate from:

- `artifacts/ui/`
  - live screenshots generated during validation runs
- `docs/architecture/validation.md#ui-baseline`
  - the current capture, comparison, and claim-boundary contract

Current rule:

- do not treat `artifacts/ui/` as the long-term golden baseline
- when we promote a screenshot into an approved reference, copy it here intentionally and document why it is acceptable
- candidate capture must produce two consecutive, fully repainted frames within the stability
  threshold before it may be compared with an approved reference

Current approved set:

- main shell
- the five top-level panels
- the AI assistant open-shell state

Current note:

- the approved main-shell and panel references keep the accepted fixed-position
  `Data Summary` table on every workflow panel; the former visible readiness
  section is intentionally absent so the sidebar remains usable at 1280 px
- the approved `ai-assistant-open.png` reference reflects the local-first setup
  state with the same fixed `Data Summary` sidebar and no duplicate readiness UI
- the approved `panel-visualization.png` reference now reflects the compact
  one-row visualization control bar used after the saliency/lazy-rendering
  stabilization work
