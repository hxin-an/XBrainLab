# XBrainLab Agent Skills

Last updated: `2026-04-19`

This document explains which skill patterns were reviewed from official and high-signal ecosystems, and which ones were selected for XBrainLab.

## Sources Reviewed

- OpenAI Codex docs:
  - [Custom instructions with AGENTS.md](https://developers.openai.com/codex/guides/agents-md)
  - [Agent Skills](https://developers.openai.com/codex/skills)
  - [Automations](https://developers.openai.com/codex/app/automations)
  - [Docs MCP](https://developers.openai.com/learn/docs-mcp)
- Anthropic official docs:
  - [Claude Code memory / CLAUDE.md](https://code.claude.com/docs/en/memory)
  - [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
  - [Claude Code hooks](https://code.claude.com/docs/en/hooks)
- High-signal GitHub ecosystems:
  - [anthropics/skills](https://github.com/anthropics/skills) - official public skills repo, about 120k GitHub stars at review time
  - [Awesome GitHub Copilot skills](https://awesome-copilot.github.com/skills/) - large public directory of reusable skills
  - [`agentmd/agent.md`](https://github.com/agentmd/agent.md) - vendor-neutral instruction-file convention

## What These Sources Consistently Recommend

Across OpenAI, Anthropic, and the larger skill ecosystem, the strongest repeated pattern is:

- keep the repo instruction file short
- keep skills focused and single-purpose
- keep trigger descriptions specific
- version control project skills with the repo
- avoid one giant omnibus skill when several narrower skills fit better

Anthropic's subagent guidance especially reinforces this pattern: focused responsibilities, clear descriptions, and version-controlled project assets perform better than broad all-in-one agents. OpenAI's skills docs similarly center reusable workflows with explicit trigger descriptions and progressive disclosure.

## Skill Families That Look Relevant

From the reviewed ecosystems, these skill families were the most relevant to XBrainLab:

- codebase knowledge / workflow baseline
  - seen in directories such as "Acquire Codebase Knowledge"
- eval-driven or test-driven refinement
  - seen in skills like "Eval Driven Dev" and "Agentic Eval"
- governance / controlled automation
  - seen in skills like "Agent Governance"
- targeted workflow automation
  - seen in Anthropic's official skills examples and automation guidance

## What We Selected For XBrainLab

### Always relevant

- `$xbrainlab-prep-gate`
  - the main stabilization-prep loop
- `$openai-docs`
  - for OpenAI, Codex, MCP, skill, plugin, and automation questions

### Repo-local workflow skills

- `$xbrainlab-repair-loop`
  - for confirmed repair-loop work
- `$xbrainlab-workflow-baseline`
  - for workflow and panel verification
- `$xbrainlab-dialog-audit`
  - for modal and dialog-heavy flows
- `$xbrainlab-real-data-validation`
  - for real EEG fixtures and cross-format validation
- `$xbrainlab-refresh-smoke`
  - for shared refresh and navigation plumbing

## What We Reviewed But Did Not Select

From the OpenAI curated skill list and public ecosystems, these were considered but not selected as standing defaults:

- generic screenshot skills
  - not selected because XBrainLab already has a Qt-native capture helper that matches the app better than a generic screenshot workflow
- Playwright or web-UI skills
  - not selected because this product is a PyQt desktop app, not a browser app
- generic frontend-design skills
  - not selected because the current mission is stabilization, not visual redesign
- security-governance skills as standing defaults
  - useful later, but not the highest-value default during the current prep-gate phase

## Local Codex Skill Review

The OpenAI curated list available through the local skill installer was also checked. The potentially relevant general-purpose options were:

- `gh-fix-ci`
- `gh-address-comments`
- `screenshot`
- `security-best-practices`
- `security-threat-model`

Current decision:

- keep GitHub-oriented skills conditional only
- do not install generic screenshot or security skills as standing defaults yet
- prefer repo-local skills for the repeated XBrainLab workflows, because they encode the project's real commands, files, and guardrails

## Practical Rule

For XBrainLab, the best skill setup is not "more skills".

It is:

- a small default set
- a few repo-local skills that match the repeated workflows
- clear separation between human-facing docs in `docs/` and agent runtime assets in `.agents/`
