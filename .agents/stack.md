# XBrainLab Agent Stack

Last reviewed: `2026-04-19`

This file records the selected agent-side setup for this repository: default skills, external reference sources, rule policy, and what the heartbeat should read before it keeps working.

## External Basis

This setup was reviewed against:

- OpenAI Codex docs for [AGENTS.md](https://developers.openai.com/codex/guides/agents-md)
- OpenAI Codex docs for [Skills](https://developers.openai.com/codex/skills)
- OpenAI Codex docs for [Automations](https://developers.openai.com/codex/app/automations)
- OpenAI docs for [Docs MCP](https://developers.openai.com/learn/docs-mcp)
- OpenAI Codex docs for [Rules](https://developers.openai.com/codex/rules)
- Anthropic Claude Code docs for [memory / CLAUDE.md](https://code.claude.com/docs/en/memory), [subagents](https://code.claude.com/docs/en/sub-agents), and [hooks](https://code.claude.com/docs/en/hooks)
- GitHub Docs for [agent skills](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills)
- the vendor-neutral [`agentmd/agent.md`](https://github.com/agentmd/agent.md) repository

## Selected Default Capabilities

These are part of the default standing setup for this repo:

- Docs MCP via `openaiDeveloperDocs`
- the built-in `openai-docs` skill
- the thread heartbeat automation attached to this conversation

## Repo Agent Files

- `.agents/stack.md`
  - the authoritative agent-side stack, skills, and rule policy
- `.agents/workflows/commit.md`
  - opt-in commit workflow, not part of the default heartbeat loop
- `.agents/workflows/tdd.md`
  - opt-in TDD workflow, only when the task explicitly wants TDD

## Skill Policy

### Required by default

- `openai-docs`
  - Use whenever the task touches OpenAI, Codex, MCP, automations, skills, plugins, or current prompting guidance.

### Conditional only

- `github:github`
  - for repo, PR, and issue orientation
- `github:gh-fix-ci`
  - for failing GitHub Actions or CI checks
- `github:gh-address-comments`
  - for unresolved review comments
- `github:yeet`
  - only when the user explicitly wants to publish changes
- `skill-installer`
  - only when we intentionally decide to evaluate or install a curated skill

### Not selected yet

- no repo-local custom skill under `.agents/skills/` yet
- no repo-local plugin for XBrainLab yet
- no standing Gmail / spreadsheet / slide / image-generation skill for this repo

Rationale:

- OpenAI and GitHub both position skills as reusable, narrowly-scoped workflows.
- Repo knowledge should stay in repo docs until a workflow repeats often enough to justify packaging as a real skill.

## Rule Policy

Durable repo rules should live in:

- `AGENTS.md`
- `.agents/stack.md`
- `docs/CODEX_SETUP.md`
- `docs/AUTOPILOT.md`
- `docs/ACTIVE_QUEUE.md`

Do not add repo-shared Codex `.rules` files yet.

Rationale:

- OpenAI documents `.rules` as user-local, machine-specific command-approval controls.
- This repo currently needs shared workflow rules more than machine-specific command prefixes.

## Human Vs Agent Boundary

- `AGENTS.md`, `.agents/stack.md`, `docs/CODEX_SETUP.md`, `docs/AUTOPILOT.md`, and `docs/ACTIVE_QUEUE.md` are the operating inputs for the agent.
- `docs/STATUS_REPORT.md` is the user-facing progress report.
- `docs/SESSION_LOG.md` and `docs/BUG_TRIAGE.md` are working records.

## Heartbeat Reading Order

Before substantial unattended work, read in this order:

1. `AGENTS.md`
2. `.agents/stack.md`
3. `docs/CODEX_SETUP.md`
4. `docs/AUTOPILOT.md`
5. `docs/ACTIVE_QUEUE.md`
6. `docs/BUG_TRIAGE.md`
7. `docs/SESSION_LOG.md`

After meaningful progress, update:

- `docs/STATUS_REPORT.md`
- `docs/SESSION_LOG.md`
- `docs/BUG_TRIAGE.md`
- `docs/ACTIVE_QUEUE.md`
