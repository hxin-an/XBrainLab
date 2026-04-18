# XBrainLab Long-Running Plan

Last updated: `2026-04-19`

This is the human-facing version of the long-running stabilization plan.

## 1. Baseline And Checkpoint

Goal:
- gather the current in-flight work into a stable, verifiable baseline before piling on more changes

We do this by:
- preserving existing work instead of wiping it
- verifying the current app and test slices in the real local environment
- checkpointing meaningful progress onto the working stabilization branch

## 2. Codex Harness And Always-On Loop

Goal:
- make the repo runnable by a long-running Codex loop without losing context

We do this by:
- keeping `AGENTS.md` short
- keeping agent runtime docs under `.agents/`
- keeping user-facing plan and progress docs under `docs/`
- using Docs MCP plus the `openai-docs` skill for OpenAI/Codex questions
- keeping a thread heartbeat running so the same conversation can continue the work

## 3. Prep Gate Before Stable Bug Fixing

Goal:
- finish the prerequisites needed before full bug-fixing mode becomes safe

Prep is only complete when:
- startup and validation commands are trustworthy
- screenshot baseline artifacts are usable
- the six main workflows have runtime-verified baselines
- high-risk dialogs have at least one live/modal validation pass
- refresh and navigation smoke protection is stronger
- risk clusters are converted into concrete bug IDs
- important runtime signals are fixed or at least clearly triaged
- local-only development and Codex assumptions are written down clearly

## 4. Repair Loop

Goal:
- once prep is complete, move into the long-running cycle of bug fixes, tests, docs, and backend/test-infra refactors

Default order:

1. dataset and load-data reliability
2. preprocess readiness and downstream state
3. training state synchronization
4. evaluation consistency
5. visualization stabilization
6. AI shell and local-only cleanup

Scope rules:

- backend/test-infra/shared non-visual plumbing can be deeply improved
- intentional layout or visual redesign still needs user discussion first
