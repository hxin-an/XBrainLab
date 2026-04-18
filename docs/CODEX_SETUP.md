# XBrainLab Codex Setup

This document is the durable operating spec for Codex work in this repository.

It complements `AGENTS.md` by holding the details that should stay versioned but should not live in the short repo-root map.

## Purpose

The goal is to let Codex keep moving on stabilization work with:

- a reliable reading order
- official-first research rules
- clear branch and checkpoint habits
- explicit validation commands
- hard stop conditions

## Source Of Truth

Use this reading order:

1. `AGENTS.md`
2. `docs/CODEX_SETUP.md`
3. `docs/AUTOPILOT.md`
4. `docs/ACTIVE_QUEUE.md`
5. `docs/BUG_TRIAGE.md`
6. `docs/SESSION_LOG.md`
7. deeper workflow or testing docs only when the current task needs them

`AGENTS.md` is the short map. `docs/` is the system of record.

## Official-First Research Rules

When the task involves OpenAI, Codex, MCP, skills, plugins, automations, or current prompting guidance:

1. use the OpenAI developer docs MCP server first
2. use the local `openai-docs` skill when it applies
3. if MCP is unavailable or insufficient, fall back only to official OpenAI domains

Do not do broad market scans by default for Codex setup questions in this repo.

## Local Codex Configuration

Required local expectations for this workspace:

- `~/.codex/config.toml` should include the OpenAI Docs MCP server as `openaiDeveloperDocs`
- the built-in `openai-docs` skill is treated as required local capability for OpenAI-related questions
- no repo-specific custom local skill should be created for XBrainLab unless repo docs prove insufficient
- the current heartbeat automation for this thread should continue the prep-first stabilization loop

## Branch And Checkpoint Policy

- Do active stabilization work on `codex/stabilization-autopilot` unless the user requests another branch.
- Do not keep long-running stabilization work on `main`.
- Treat existing dirty worktree changes as in-progress work to preserve, not as noise to wipe.
- Checkpoint meaningful progress on the working branch after validation so unattended work is resumable.

## Validation Commands

Run from the current workspace root:

```bash
/home/administrator/.local/bin/poetry run python run.py
timeout 25s xvfb-run -a /home/administrator/.local/bin/poetry run python run.py
xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py
/home/administrator/.local/bin/poetry run pytest -s tests/unit/backend/training/test_option.py -q
/home/administrator/.local/bin/poetry run pytest -s tests/unit/ui/test_main_window_sync.py -q
/home/administrator/.local/bin/poetry run pytest -s tests/integration/io/test_io_integration.py -q
/home/administrator/.local/bin/poetry run pytest -s tests/unit/ui -q
```

Current local note:

- In the current `/mnt/d/repos/XBrainLab` Codex workspace, default `pytest` capture is not trustworthy yet and can fail at teardown with `FileNotFoundError` inside `_pytest/capture.py`.
- Until that is repaired, use `-s` for local validation in this workspace and record the limitation in triage.

## Prep Gate

Do not switch the queue into normal repair mode until all of the following are true:

- startup and validation commands are trustworthy and documented
- screenshot baseline capture produces a usable non-black artifact
- the six main workflows have runtime-verified baselines
- high-risk dialogs have at least one live/modal validation pass recorded
- refresh and navigation smoke protection is strong enough for shared UI changes
- current risk clusters have been converted into concrete bug IDs and priorities
- notable runtime signals are either fixed or triaged into reproducible issues
- local-only development and Codex operating assumptions are written down clearly

## Default Work Loop

For each unattended or manual Codex work cycle:

1. read `AGENTS.md`, `docs/CODEX_SETUP.md`, `docs/AUTOPILOT.md`, and `docs/ACTIVE_QUEUE.md`
2. pick the top eligible item
3. reproduce the issue or confirm the current behavior
4. add the narrowest useful test or capture the best available evidence
5. make the smallest effective fix or supporting refactor
6. run the smallest relevant validation slice
7. re-run broader UI safety tests if shared UI plumbing changed
8. update `docs/BUG_TRIAGE.md`, `docs/BACKLOG.md`, `docs/SESSION_LOG.md`, and `docs/ACTIVE_QUEUE.md`
9. continue unless a stop condition is hit

## Stop Conditions

Pause and wait for the user when any of these become true:

- the change would intentionally alter layout or visual design
- a user-facing workflow would be fundamentally reshaped
- a large architectural rewrite is required outside the allowed backend/test-infra scope
- risky system changes outside the repo or local Codex setup are required
- the bug has multiple plausible product directions and the right one is not obvious

## Allowed Deep Work

Aggressive redesign is allowed only in:

- backend state, services, facades, and controller boundaries
- load-data pipeline and related import infrastructure
- shared non-visual UI plumbing
- test infrastructure, fixtures, and harness

It is not allowed for:

- panel composition redesign
- sidebar arrangement redesign
- dialog visual redesign
- any intentional change to user-accepted layout structure
