# XBrainLab Codex Setup

This document is the canonical setup and operating spec for Codex work in this repository.

It holds the durable agent-side rules that should not live in the short repo-root `AGENTS.md`.

## Purpose

The goal is to let Codex keep moving on stabilization work with:

- a reliable reading order
- explicit separation between human-facing docs and agent runtime docs
- official-first research rules
- clear branch and checkpoint habits
- explicit validation commands
- hard stop conditions

## Canonical Layout

- `AGENTS.md`
  - short repo map and guardrails
- `.agents/stack.md`
  - selected skills, external references, rule policy, and heartbeat reading order
- `.agents/runbooks/*.md`
  - canonical agent runtime docs
- `.agents/skills/*/SKILL.md`
  - repo-local reusable workflows
- `docs/*.md`
  - human-facing plan, status, triage, workflow, and testing docs

## Source Of Truth

Use this reading order:

1. `AGENTS.md`
2. `.agents/stack.md`
3. `.agents/runbooks/setup.md`
4. `.agents/runbooks/autopilot.md`
5. `.agents/runbooks/active-queue.md`
6. `docs/PLAN.md`
7. `docs/STATUS_REPORT.md`
8. `docs/BUG_TRIAGE.md`
9. `docs/SESSION_LOG.md`
10. deeper workflow or testing docs only when the current task needs them

Interpretation:

- `.agents/` is the canonical operating surface for the agent.
- `docs/` is the human-facing and project-record surface.

## Official-First Research Rules

When the task involves OpenAI, Codex, MCP, skills, plugins, automations, or current prompting guidance:

1. use the OpenAI developer docs MCP server first
2. use the local `openai-docs` skill when it applies
3. if MCP is unavailable or insufficient, fall back only to official OpenAI domains

When evaluating better agent setup patterns, it is acceptable to additionally consult:

- Anthropic Claude Code official docs
- GitHub official docs for agent skills
- high-signal GitHub repositories that show reusable skill and agent-layout patterns

## Local Codex Configuration

Required local expectations for this workspace:

- `~/.codex/config.toml` should include the OpenAI Docs MCP server as `openaiDeveloperDocs`
- the built-in `openai-docs` skill is treated as required local capability for OpenAI-related questions
- `.agents/stack.md` should be kept current when the selected skill, rule, or heartbeat setup changes
- repo-local reusable workflows should live in `.agents/skills/`
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

1. read `AGENTS.md`, `.agents/stack.md`, `.agents/runbooks/setup.md`, `.agents/runbooks/autopilot.md`, and `.agents/runbooks/active-queue.md`
2. activate the most relevant repo-local skill when the task clearly matches one
3. pick the top eligible item
4. reproduce the issue or confirm the current behavior
5. add the narrowest useful test or capture the best available evidence
6. make the smallest effective fix or supporting refactor
7. run the smallest relevant validation slice
8. re-run broader UI safety tests if shared UI plumbing changed
9. update `docs/BUG_TRIAGE.md`, `docs/BACKLOG.md`, `docs/SESSION_LOG.md`, `docs/STATUS_REPORT.md`, and `.agents/runbooks/active-queue.md`
10. continue unless a stop condition is hit

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
