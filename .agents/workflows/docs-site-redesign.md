# Workflow: Documentation Site Redesign

Use `docs-site-product-designer` as primary. Add `docs-curator` for content authority and
`ui-product-reviewer` for visual review.

## Brief

1. Inspect `mkdocs.yml`, the landing page, current status page, theme overrides, and only verified
   artifacts proposed for display.
2. Define audiences, top tasks, first-screen questions, navigation hierarchy, and non-goals.
3. Separate current status, guides, architecture/target, validation evidence, and history.

## Implement

- Prefer existing pages, Material primitives, and bounded CSS.
- Do not edit generated `site/`, add a mirrored documentation source directory, or promote
  worklogs/records to primary navigation.
- Verify every artifact path and identity before linking it.
- Do not create product claims to fill a visual component.

## Validate

1. Run `poetry run -- mkdocs build --strict`.
2. Capture desktop and narrow screenshots when layout/CSS changes.
3. Inspect hierarchy, contrast, wrap/overflow, cards/tables, focus, scroll, broken media, and claims.
4. Report source files, build result, visual evidence, and unresolved browser/aesthetic decisions.
