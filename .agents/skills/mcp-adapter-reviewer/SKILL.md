---
name: mcp-adapter-reviewer
description: "Use only for explicitly requested XBrainLab MCP adapter work covering transports, tools/list, tools/call, authorization, sessions, and application enforcement. Never invoke implicitly."
---

# MCP Adapter Reviewer

Stop unless the user explicitly requested MCP work. The presence of MCP code, tests, an artifact,
or a general security/architecture review is not permission to load or apply this skill.

## Workflow

1. Record the explicitly requested transport, client, session mode, and threat boundary.
2. Read only the matching adapter code and MCP-specific docs/tests.
3. Verify discovery schemas are projections of the application command registry.
4. Verify every call uses application admission, confirmation, structured result, and capability
   policy rather than controller/private state.
5. For stdio, protect protocol stdout and subprocess lifecycle.
6. For HTTP, check authentication, origin/network defaults, body limits, session ownership,
   cancellation, progress, resource locks, and bounded retention.
7. Separate headless-session evidence from desktop-control claims.

## Output

Report adapter boundary, bypasses, transport/security risks, client evidence, missing tests, and
claims that the requested scope cannot support. Do not add MCP to general handoff gates.
