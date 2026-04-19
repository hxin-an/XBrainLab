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

## Product Definition Reminder

Keep the assistant roles separate:

- Codex in this repository is the external development assistant.
- the in-app XBrainLab assistant is a workflow-aware software-operation agent inside the product.

For the in-app assistant:

- humans and the in-app assistant are two control modes over the same software capability surface
- direct UI control and agent tool control should stay conceptually aligned
- the current tool taxonomy is redesignable and should be changed if a better workflow-oriented action surface is needed

## Canonical Layout

- `AGENTS.md`
  - short repo map and guardrails
- `.agents/stack.md`
  - selected skills, external references, rule policy, and heartbeat reading order
- `.agents/runbooks/*.md`
  - canonical agent runtime docs
- `.agents/skills/*/SKILL.md`
  - repo-local reusable workflows
- `docs/current/*.md`
  - the human-facing now/plan/triage surface
- `docs/workflows/*.md`
  - workflow maps, testing strategy, and risk references
- `docs/history/*.md`
  - session history and backlog
- `docs/archive/reference/AGENT_SKILLS.md`
  - human-facing background on skill selection, not a required read for each cycle

## Source Of Truth

Use this reading order:

1. `AGENTS.md`
2. `.agents/stack.md`
3. `.agents/runbooks/setup.md`
4. `.agents/runbooks/autopilot.md`
5. `.agents/runbooks/active-queue.md`
6. `docs/current/PLAN.md`
7. `docs/current/STATUS_REPORT.md`
8. `docs/current/BUG_TRIAGE.md`
9. `docs/history/SESSION_LOG.md`
10. deeper workflow or testing docs only when the current task needs them

Interpretation:

- `.agents/` is the canonical operating surface for the agent.
- `docs/current/` is the human entry point for current status.
- `docs/workflows/` and `docs/history/` are deeper support docs.

## Official-First Research Rules

When the task involves OpenAI, Codex, MCP, skills, plugins, automations, or current prompting guidance:

1. use the OpenAI developer docs MCP server first
2. use the local `openai-docs` skill when it applies
3. if MCP is unavailable or insufficient, fall back only to official OpenAI domains

When evaluating better agent setup patterns, it is acceptable to additionally consult:

- Anthropic Claude Code official docs
- GitHub official docs for agent skills
- high-signal GitHub repositories that show reusable skill and agent-layout patterns

When evaluating the in-app XBrainLab assistant specifically:

- do not limit research to OpenAI platform patterns
- also consult Anthropic tool-use guidance, relevant agent papers, and high-signal open-source agent implementations
- keep the product definition straight:
  - Codex is the external development assistant
  - the in-app assistant is a workflow-aware software-operation agent for XBrainLab itself
  - the human user and the in-app assistant should be treated as two control modes over the same capability surface

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
/home/administrator/.local/bin/poetry run python scripts/dev/update_quality_dashboard.py
/home/administrator/.local/bin/poetry run pytest --capture=sys tests/unit/backend/training/test_option.py -q
/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui/test_main_window_sync.py -q
/home/administrator/.local/bin/poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q
/mnt/d/repos/XBrainLab/scripts/dev/run_ui_pytest.sh tests/unit/ui -q
```

Current local note:

- In the current `/mnt/d/repos/XBrainLab` Codex workspace, unattended UI pytest runs need explicit headless Qt env because `pytest-qt` can otherwise abort during `qapp` setup while trying to load `xcb` or `wayland`.
- Use `scripts/dev/run_ui_pytest.sh` for unattended or heartbeat-driven UI pytest commands; it applies `QT_QPA_PLATFORM=offscreen`, `MPLBACKEND=Agg`, `MPLCONFIGDIR=/tmp/matplotlib-codex`, and `--capture=sys`.
- Use `scripts/dev/update_quality_dashboard.py` when you want one current health snapshot instead of reading multiple test logs manually.
- The older `fd`-capture teardown issue has become inconsistent and should stay in triage until it is either re-reproduced reliably or retired.

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
9. update `docs/current/BUG_TRIAGE.md`, `docs/history/BACKLOG.md`, `docs/history/SESSION_LOG.md`, `docs/current/STATUS_REPORT.md`, and `.agents/runbooks/active-queue.md`
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
