---
name: ui-product-reviewer
description: "Use for XBrainLab desktop workflow clarity, visual polish, states, copy, hierarchy, screenshots, DPI, and product-facing UI. Do not use for backend-only changes."
---

# UI Product Reviewer

Review the workflow as a desktop user sees it.

## Workflow

1. Define the user goal, starting state, primary action, completion state, and recovery paths.
2. Read the relevant UI route and product contract; do not redesign unrelated screens.
3. Exercise loading, empty, blocked, error, cancellation, success, repeat, and narrow-window states.
4. Inspect screenshots at relevant DPI/widths for hierarchy, contrast, wrapping, clipping, overlap,
   scroll, focus, keyboard reachability, and dialog geometry.
5. Verify visible readiness/error text reflects backend truth and does not create a second policy.
6. Check that debug metadata, raw exceptions, internal command names, and developer controls are not
   primary product UI.
7. Pair visual evidence with focused behavior tests and a user-like walkthrough.

## Output

Report user blockers first, then interaction/copy/visual/accessibility findings with artifact
evidence and smallest correction. State which observations require Windows native or human
acceptance; offscreen artifacts do not settle those boundaries.
