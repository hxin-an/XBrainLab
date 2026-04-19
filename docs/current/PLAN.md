# XBrainLab Long-Running Plan

Last updated: `2026-04-19`

This is the human-facing version of the long-running thesis plan.

The thesis currently has three connected workstreams:

1. stabilize the existing application
2. redesign the tool-call agent architecture
3. validate the system rigorously enough for thesis claims

Current execution order:

- stabilization first
- agent redesign second
- rigorous validation throughout, with deeper evaluation becoming a first-class track before final thesis claims

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

## 5. Tool-Call Agent Redesign

Goal:
- redesign the tool-call agent architecture only after the stabilization floor is strong enough to support trustworthy iteration

Working rules:

- use `docs/decisions/` as the canonical design home
- prefer a small number of active ADRs over many scattered planning notes
- explicitly document tradeoffs, rejected alternatives, and evaluation assumptions
- do not treat old design notes as automatically current without checking the code and validation evidence

Expected outputs:

- clear problem statement
- explicit product definition for the in-app assistant
- candidate architectures
- selected execution model
- redesigned tool surface around workflow intent rather than legacy tool boundaries
- safety and verification boundaries
- evaluation plan inputs for thesis experiments

## 6. Rigorous Validation

Goal:
- build repeatable evidence that can support thesis arguments, not just engineering confidence

Validation work should cover:

- workflow-level reliability checks for the application itself
- tool-call accuracy or task-success evaluation for the agent redesign
- baseline comparisons and failure-case documentation
- reproducible commands, datasets, and reporting structure

Near-term rule:

- every major design claim should eventually map to a test, runtime observation, benchmark, or documented experiment plan
- quality monitoring should stay two-speed:
  - fast, high-frequency gates catch new regressions quickly
  - slower full gates continue surfacing existing debt until it is deliberately paid down
