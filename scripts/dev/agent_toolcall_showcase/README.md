# Agent Tool-Call Showcase

This command is a fast product showcase and diagnostic. It is not the frozen
thesis benchmark, does not calculate Agent accuracy, and must not be cited as
thesis evidence.

From the repository root:

```bash
poetry run -- python scripts/dev/run_agent_toolcall_showcase.py
```

Useful selections:

```bash
poetry run -- python scripts/dev/run_agent_toolcall_showcase.py --list-cases
poetry run -- python scripts/dev/run_agent_toolcall_showcase.py --case 'import.*'
poetry run -- python scripts/dev/run_agent_toolcall_showcase.py --area training
poetry run -- python scripts/dev/run_agent_toolcall_showcase.py --details
poetry run -- python scripts/dev/run_agent_toolcall_showcase.py \
  --resume build/dev-artifacts/agent-toolcall-showcase/latest.json
```

Use the exact product model only when its pinned cache already exists:

```bash
poetry run -- python scripts/dev/run_agent_toolcall_showcase.py \
  --real-granite \
  --model-cache-dir <existing-model-cache> \
  --case import.scan_source
```

`--real-granite` forces offline model loading. It never downloads a model and
never substitutes another model. Missing runtime assets produce redacted JSON
and Markdown failure reports and a nonzero exit.

Resume is fail-closed evidence reuse, not a cache that upgrades old output. A
resume report must match the current Git commit, current product/showcase source
fingerprint, selector ID/version, and every selected prompt/case identity. Real
Granite reports must also match the exact model ID and revision and retain the
offline/no-fallback policy. Older schemas or mismatched identities are rejected.

Prior `pass`, summary, terminal, failure, and prose fields are not copied as
authority. The runner copies only an explicit structured allowlist, regenerates
case-authored display values, and reruns the current contract for successful,
blocked, cancelled, stale, retry, handoff, and approved-confirmation outcomes.
A prior case that no longer satisfies the contract executes again. Resumed cases
are marked as not executed in the current run and do not carry prior state dumps,
messages, raw model output, paths, or arbitrary keys into the new artifact.

Output defaults to:

- `build/dev-artifacts/agent-toolcall-showcase/latest.json`
- `build/dev-artifacts/agent-toolcall-showcase/latest.md`

Override them with `--json-out` and `--markdown-out`. The default workflow also
writes one compact deterministic FIF under the same `build/` output directory.
No EEG or model data is downloaded.

For a matrix run, stdout contains the summary and compact case table. Add
`--details` (or `--verbose`) to print every case detail. A single `--case`
selection prints its detail automatically. The JSON and Markdown artifacts are
complete for cases executed in that run, including each prompt,
state/capability context, exposed schemas, proposal, verification,
confirmation/handoff, command result, state delta, visible response, duration,
and terminal pass/fail. Resumed cases contain only the current case contract and
allowlisted structured terminal evidence. Authorized paths and host-only
confirmation values use field-aware public projections; paths and secrets are
never emitted. Any failed or missing terminal outcome makes the overall process
exit nonzero, even if an internal summary incorrectly says `passed`.
