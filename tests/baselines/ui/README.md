# XBrainLab UI Reference Baselines

This directory contains deliberately approved visual regression references. It is separate from:

- ignored candidate captures in `build/dev-artifacts/ui-baseline/`;
- exact-source handoff evidence in `build/handoff-evidence/<full-SHA>/`;
- the evidence and manual-acceptance contract in `docs/validation/README.md`.

References detect visual drift; they do not certify product aesthetics, Windows-native behavior, or
human acceptance. A candidate must produce two consecutive fully repainted frames within the
stability threshold before comparison.

The candidate directory also contains `ui-baseline-evidence.json`, binding the source digest,
capture environment, candidate hashes, reference hashes, and per-image comparison result. The
capture command never updates this directory; reference changes are an explicit reviewed commit.

The approved set covers the main shell, five workflow panels, the Assistant open-shell state,
and the Filter dialog's complementary Band-pass/Notch On/Off states.
Updates are intentional review decisions, never copies from a mutable `latest` artifact.
