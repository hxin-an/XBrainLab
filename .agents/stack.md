# XBrainLab Agent Stack

Last reviewed: `2026-04-19`

This file records the selected agent-side setup for this repository: default skills, external reference sources, canonical agent runbooks, rule policy, and what the heartbeat should read before it keeps working.

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
- the repo-local `$xbrainlab-prep-gate` skill while prep is active
- the thread heartbeat automation attached to this conversation

## Repo Agent Files

- `.agents/stack.md`
  - the authoritative agent-side stack, skills, and rule policy
- `.agents/runbooks/setup.md`
  - canonical agent setup and operating rules
- `.agents/runbooks/autopilot.md`
  - canonical unattended loop definition
- `.agents/runbooks/active-queue.md`
  - canonical unattended queue
- `.agents/skills/xbrainlab-prep-gate/SKILL.md`
  - repo-local prep-gate workflow skill
- `.agents/skills/xbrainlab-repair-loop/SKILL.md`
  - repo-local repair-loop workflow skill
- `.agents/skills/xbrainlab-workflow-baseline/SKILL.md`
  - runtime workflow and panel baseline skill
- `.agents/skills/xbrainlab-dialog-audit/SKILL.md`
  - dialog and modal acceptance audit skill
- `.agents/skills/xbrainlab-real-data-validation/SKILL.md`
  - real EEG fixture and cross-format validation skill
- `.agents/skills/xbrainlab-refresh-smoke/SKILL.md`
  - shared refresh and navigation smoke skill
- `.agents/workflows/commit.md`
  - opt-in commit workflow, not part of the default heartbeat loop
- `.agents/workflows/tdd.md`
  - opt-in TDD workflow, only when the task explicitly wants TDD

## Skill Policy

### Required by default

- `openai-docs`
  - Use whenever the task touches OpenAI, Codex, MCP, automations, skills, plugins, or current prompting guidance.
- `xbrainlab-prep-gate`
  - Use for the repeated stabilization prep loop until prep is complete.

### Conditional only

- `xbrainlab-repair-loop`
  - use after prep is complete, or for clearly confirmed repair-loop items
- `xbrainlab-workflow-baseline`
  - use for workflow mapping, panel verification, and baseline refresh
- `xbrainlab-dialog-audit`
  - use for dialog and modal acceptance auditing
- `xbrainlab-real-data-validation`
  - use for real EEG fixture and cross-format validation
- `xbrainlab-refresh-smoke`
  - use for shared refresh and navigation checks
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

- no repo-local plugin for XBrainLab yet
- no standing Gmail / spreadsheet / slide / image-generation skill for this repo

Rationale:

- OpenAI and GitHub both position skills as reusable, narrowly-scoped workflows.
- Repo knowledge stays in docs and runbooks, while repeated workflows are now packaged as repo-local skills under `.agents/skills/`.
- Anthropic's official subagent guidance also favors focused, single-purpose units over one broad do-everything agent.

## Ecosystem Review Notes

The strongest external patterns we found were:

- Anthropic's official docs and public `anthropics/skills` repository favor focused, reusable skills and version-controlled project assets.
- Awesome GitHub Copilot's large public skill directory highlights codebase-knowledge, eval-driven development, and governance as common reusable patterns.
- OpenAI's own Codex docs favor explicit trigger descriptions, progressive disclosure, and pairing Docs MCP with a narrow doc skill for current product questions.

For XBrainLab, that translated into a small set of repo-local workflow skills instead of a large bucket of generic installs.

## Rule Policy

Durable repo rules should live in:

- `AGENTS.md`
- `.agents/stack.md`
- `.agents/runbooks/setup.md`
- `.agents/runbooks/autopilot.md`
- `.agents/runbooks/active-queue.md`

Do not add repo-shared Codex `.rules` files yet.

Rationale:

- OpenAI documents `.rules` as user-local, machine-specific command-approval controls.
- This repo currently needs shared workflow rules more than machine-specific command prefixes.

## Human Vs Agent Boundary

- `AGENTS.md`, `.agents/stack.md`, `.agents/runbooks/*.md`, and `.agents/skills/*/SKILL.md` are the operating inputs for the agent.
- `docs/current/PLAN.md`, `docs/current/STATUS_REPORT.md`, and `docs/current/BUG_TRIAGE.md` are the main human-facing current-state docs.
- `docs/workflows/*.md` are supporting workflow and risk references.
- `docs/history/*.md` are working records and long-running context.
- `docs/reference/AGENT_SKILLS.md` is human-facing background on skill selection, not part of the default heartbeat read.

## Heartbeat Reading Order

Before substantial unattended work, read in this order:

1. `AGENTS.md`
2. `.agents/stack.md`
3. `.agents/runbooks/setup.md`
4. `.agents/runbooks/autopilot.md`
5. `.agents/runbooks/active-queue.md`
6. `docs/current/PLAN.md`
7. `docs/current/STATUS_REPORT.md`
8. `docs/current/BUG_TRIAGE.md`
9. `docs/history/SESSION_LOG.md`

After meaningful progress, update:

- `.agents/runbooks/active-queue.md`
- `docs/current/STATUS_REPORT.md`
- `docs/history/SESSION_LOG.md`
- `docs/current/BUG_TRIAGE.md`
