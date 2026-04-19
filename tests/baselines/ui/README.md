# XBrainLab UI Reference Baselines

This directory stores approved UI reference artifacts.

Use it for curated "known-good" screenshots that UI regression checks compare against.

Keep this separate from:

- `artifacts/ui/`
  - live screenshots generated during validation runs
- `docs/workflows/UI_BASELINE.md`
  - the human-readable definition of what "structurally correct" means

Current rule:

- do not treat `artifacts/ui/` as the long-term golden baseline
- when we promote a screenshot into an approved reference, copy it here intentionally and document why it is acceptable

Current approved set:

- main shell
- the five top-level panels
- the AI assistant open-shell state
