---
name: docs-site-product-designer
description: "Use for XBrainLab MkDocs portal IA, Material layouts, artifact galleries, visual hierarchy, responsiveness, and screenshots. Do not use for routine truth sync."
---

# Docs Site Product Designer

Treat the documentation site as a product portal, not a source-tree browser.

## Workflow

1. Confirm the root UI/docs-site mutation boundary before editing layout, CSS, navigation, or copy.
2. Identify primary audiences and the top tasks each must complete.
3. Read the current MkDocs navigation, landing page, theme overrides, and only the artifacts being
   surfaced.
4. Sketch the navigation and page hierarchy before editing layout.
5. Reuse Material primitives and existing design tokens; keep custom CSS bounded.
6. Build with `mkdocs build --strict`.
7. Capture desktop and narrow screenshots; inspect hierarchy, wrapping, contrast, focus, scroll,
   broken media, and empty states.

## Boundaries

- Do not make historical evidence look current.
- Do not link generated artifacts whose existence and identity were not verified.
- Avoid decorative cards that add clicks without improving task discovery.
- Keep content truth changes with `docs-curator`; use this skill for portal presentation.

## Output

Report audience/task map, navigation changes, visual review evidence, accessibility risks, and
remaining browser/platform boundaries.
