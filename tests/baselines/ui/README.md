# XBrainLab UI Reference Baselines

This directory is reserved for approved UI reference artifacts.

Use it for curated "known-good" screenshots that future UI regression checks can compare against.

Keep this separate from:

- `artifacts/ui/`
  - live screenshots generated during validation runs
- `docs/workflows/UI_BASELINE.md`
  - the human-readable definition of what "structurally correct" means

Current rule:

- do not treat `artifacts/ui/` as the long-term golden baseline
- when we promote a screenshot into an approved reference, copy it here intentionally and document why it is acceptable

Planned first use:

- main shell
- the five top-level panels
- the AI assistant open-shell state
