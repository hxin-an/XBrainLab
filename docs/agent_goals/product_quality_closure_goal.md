# Product Quality Closure Goal

## Objective

Turn the clean `ux/assistant-product-v1` candidate into a reviewed, pushed
Windows handoff candidate by closing the verified architecture, security,
functional, Agent, UI/UX, validation, documentation and repository-hygiene
findings in `docs/records/product_quality_audit_2026-07-30.md`.

This is not complete when one test passes or one reviewer says PASS. It is
complete only when every automated hard gate below passes from the same clean
commit and the remaining boundary is limited to human Windows acceptance.

## Baseline and Ownership

- Start from clean commit `3869aaef73acf3fb30ce95d15868c2abcf17c6f5`.
- Use integration branch `stabilize/product-quality-closure`.
- Never stage, rewrite, revert or hide repo-root `settings.json` or
  `.vscode/settings.json`.
- Do not touch the dirty `stabilize/windows-public-beta` worktree. Packaging
  work is integrated only after its owner creates an independently validated
  clean commit.
- Preserve all unrelated user and parallel-agent changes. Stop and report a
  real same-file ownership conflict instead of guessing.
- Store large fixtures, artifacts and caches on D. Before bounded workers,
  check disk/session growth and follow AGENTS.md native-test rules.

## Delivery Sequence

1. Keep the audit ledger current. Add new reproducible findings instead of
   hiding them behind a narrow fix.
2. Close P0/P1 security and functional correctness findings with test-first
   slices.
3. Close Application/Command API state-boundary findings one command family at
   a time. Do not add another facade or compatibility fallback.
4. Close Granite/RAG/runtime and Agent lifecycle findings without weakening
   capability, verification or confirmation policy.
5. Close UI/UX findings with exact-source artifacts and a same-class sweep.
6. Replace weak product claims with real ApplicationService, deterministic
   oracle and strict multi-dataset evidence.
7. Rewrite canonical current truth, remove stale active-goal material and prune
   duplicate current artifacts.
8. Run independent reviewer gates, then have the main agent re-read the diff,
   re-run evidence and inspect artifacts.
9. Commit and push every validated slice. Produce one final clean exact-SHA
   handoff report.

## Product Decisions

- Product local model: exact-only
  `ibm-granite/granite-3.3-2b-instruct@707f574c62054322f6b5b04b6d075f0a8f05e0f0`.
- Product RAG embedding:
  `sentence-transformers/all-MiniLM-L6-v2@1110a243fdf4706b3f48f1d95db1a4f5529b4d41`,
  Apache-2.0, explicit consent/quota preflight, offline-only runtime.
- Phi models are not product choices and never become fallback.
- Stop Training is terminal cancellation; implicit resume is not supported.
- Product persistence never deserializes unsafe legacy pickle artifacts.
- Application publication is the state-changing UI truth. A revision is
  acknowledged only after a consumer reports successful visible delivery.
- Product command results contain immutable DTOs, not live backend objects.
- MCP and thesis benchmark work are outside this goal.

## Hard Gates

Use bounded reviewers for architecture/clean code, security/privacy,
EEG/functional correctness, Agent, UI product quality and test/docs quality.
No worker inherits the complete conversation. Run at most four in parallel.
Worker verdicts are inputs, not completion.

The main agent must prove:

- no code-controllable P0/P1 audit item remains open;
- no product `torch.load(..., weights_only=False)`;
- no Application-layer import of controller code on migrated product paths;
- no default legacy automation command or silent readiness/model fallback;
- Stop-at-optimizer-boundary then Start runs only the new plan;
- publication no-render does not acknowledge or lose terminal events;
- malicious persistence/path/link/RAG/context cases fail safely;
- a real temporary FIF crosses ApplicationService import, preprocess, epoch,
  split, train, evaluate and visualize without mocked persistence;
- the deterministic oracle proves labels, disjoint splits and held-out outputs;
- required fixture manifest and multi-dataset gates pass with no hidden skip,
  xfail or deselection;
- real Granite and secure offline RAG cover success, confirmation, error,
  retry, cancel and long-session behavior;
- required full/narrow/DPI screenshots are readable and personally inspected;
- Ruff, full Basedpyright, architecture checks, regression pytest, strict
  MkDocs and quality dashboard pass from the same commit;
- worktree is clean, all checkpoints are pushed, protected settings and the
  dirty packaging worktree are unchanged.

## Completion Boundary

When all automated gates pass, update the audit to `verified`, synchronize
canonical docs and mark the branch as a Windows handoff candidate. Do not merge
to `main` and do not claim product completion until the user finishes native
Windows click-through acceptance, including DPI/multi-monitor, interactive 3D
and teacher-supplied datasets.
