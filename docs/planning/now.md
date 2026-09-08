# XBrainLab Now

最後更新：`2026-09-08`

## Active — Logging clarity and preprocess latency investigation

### Problem and evidence

- User reports repeated `Adding metadata with 1 columns` messages and slow preprocessing.
  Message frequency alone does not establish the latency cause; Apply measurements below identify
  numerical filtering as the dominant cost in the representative workloads.
- Assistant cleanup #120 is merged after the user's complete walkthrough acceptance. Its bounded
  model limits remain unchanged; no prompt/RAG tuning or Stable promotion belongs to this slice.

### Outcome and scope

- Identify noisy message producers and propose appropriate normal/debug/warning/error behavior.
  Preserve actionable failures, native-crash evidence and diagnostic redaction.
- Trace user operation → shared command service → preprocessing → result publication/UI refresh.
  Measure first and repeated operations separately; distinguish compute, copy/validation, queue,
  publication and rendering costs before choosing a repair.
- Non-goals: UI layout/interaction changes, global log suppression, a new logging/control framework,
  broad SHA/cache removal, scientific algorithm changes, model experiments or unrelated legacy cleanup.
- UI approval: user explicitly authorizes internal UI threading/callback/progress-frequency repairs,
  preserving layout, copy, controls and workflow. No new visible presentation is authorized.
- Approved implementation: independent logging and preprocess workers, integrated by coordinator
  and independently reviewed. Logging covers all workflows with bounded repairs. Preprocess focuses
  on Apply waiting across recordings; compare safe thread parallelism (at most two workers) against
  serial after removing demonstrated redundant work. Keep only measured wins, preserve atomic
  publication/cancel/order and avoid nested parallelism or new public settings.

### Investigation and bounded repair sequence

1. Logging track: inspect existing logger/handlers and MNE integration; capture a representative
   operation's output, attribute repeated messages to their actual producer, and distinguish
   duplicates from useful progress. Do not assume every repeated message is an error.
2. Preprocess track: use existing native lifecycle/scenario tooling where applicable. Freeze data,
   parameters, source and environment; measure first operation and repeated/reset/reapply cases.
   Include a small baseline and a representative larger dataset already available locally.
   Do not download data/models or introduce permanent per-call instrumentation by default.
3. Compare numerical preprocessing time with surrounding copies, hashes, validation and UI work.
   Inspect code alongside measurements, including async completion/cancel/repeat and resource release.
   Classify findings as must-fix, worthwhile simplification or justified retention.
4. Keep the two investigations independent when ownership permits. Shared logger/preprocess seams
   must have one editing owner; integrate only after tracing their interaction.
5. Before product edits, narrow the active plan to an evidenced repair with affected callers,
   deletion candidates and focused tests. Separate log and performance PRs unless one root cause
   directly requires both. No broad rewrite to satisfy an audit.

### Validation and endpoint

- Logging repair: test actual emitted records/output and meaningful failures, preserving redaction
  and warning/error visibility; do not only mock logger calls.
- Performance repair: compare identical inputs/results before/after, including repeat/cancel and
  relevant metadata/event invariants; report measured distributions and environment, not a
  universal speedup from one timing.
- Native checks use bounded timeout and `prlimit --core=0`. Use focused L0/L1 locally; reuse exact-head
  CI for formal regression and add only missing applicable native/data evidence.
- Current endpoint: implement evidenced repairs, reviewed PRs and Windows manual-test delivery. Product handoff after
  implementation requires independent risk review, applicable same-head CI and exact-source native
  manual testing. Product merge still requires explicit user acceptance.
- Current evidence: metadata lines originate from MNE's metadata property setter during per-source
  provenance assignment. Logging candidate sets normal desktop MNE verbosity once at startup to
  WARNING while preserving explicit MNE_LOGGING_LEVEL configuration; no message blacklist.
- Apply baseline (three recordings, three reset-equivalent cycles): Zhou2020 0.618–0.753 s and
  GDF fixtures 1.849–2.095 s, dominated by MNE work. No SHA hotspot was found in this command path.
  The redundant service copy was removed; processor-owned detached copies retain rollback isolation.
- Two workers help Zhou2020 but not the small GDF fixture: six Zhou recordings median 1.291 s serial
  versus 0.783 s with two workers; the GDF median was within noise (1.737 versus 1.723 s). One
  complete local Zhou batch (85 EDFs, 41 channels, about 197,000 samples at 500 Hz each) has
  three candidate Apply observations with median 11.417 s. Comparable direct-loader observations
  measured old-source serial 18.582/18.764 s versus candidate 11.349 s; peak RSS remained about
  5.4 GiB. Loading is measured separately; these are local workload results, not universal claims.
- Candidate repair limits parallel work to two independent Filter/Resample recordings, schedules only
  one completed pair at a time, propagates only the owned-work context, falls back to serial for a
  duplicate MNE instance, and keeps one final atomic publication. Focused backend, cancellation,
  alias and native async/render evidence pass. Consecutive Filter → Resample outputs match serial
  data, history and events on twelve recordings. Independent review is complete; next is exact-head
  PR CI and Windows handoff, not a new cache, public setting or scheduler owner.
- First PR #122 CI exposed three remaining in-place test processors in controller/integration
  tests that bypass the shipped processor copy boundary. The failed-run evidence is retained;
  corrected tests use real detached processing and assert signal/history isolation. All three
  reproduced red then passed; independent review confirmed no production in-place provider.
  Next: final exact-head CI and Windows handoff; product source is unchanged from the measured candidate.
- The next CI run passed preprocessing and Windows checks but exposed a macOS saliency test
  racing a queued refresh: the compute/render flag alone does not identify the displayed error state.
  Correct only the test to wait for both the released flag and the actual render-error text within
  its existing timeout. Preserve compute-success and result-identity assertions and the failed artifact;
  review and focused validation precede another exact-head CI run. No saliency product change.

## Following work — agreed order

- After logging/preprocess, audit frontend → backend → tests by user workflow: data preparation,
  training and results. Inspect repeated calculations/validation, SHA, caches, state ownership,
  compatibility branches, async lifecycle and high-mock tests. Use small justified PRs.
- Then establish experimental datasets and an evaluator that represents actual product RAG,
  first-generation model decisions, Host intervention and final product outcomes separately.
  Keep held-out English cases and small-model context budgets explicit.
- Only afterward conduct prompt/RAG/architecture improvement experiments. The existing frozen
  81-case suite remains bounded regression evidence, not a complete capability evaluation.

## Retained evidence limits

- Historical native -11/debug timeout causes remain unproven; added diagnostics are not root-cause fixes.
- Fresh contextless Codex takeover remains unverified after environment/permission restrictions;
  guidance audits do not establish identical fresh-agent behavior.
- Protect root dirty work/settings, original datasets, shared model/runtime caches and durable evidence.
  Remove merged task worktrees/disposable outputs only after checking identity and active use.

## Source of truth

Git/PRs own versions and approvals; docs/current.md owns product claims. Completed implementation
history belongs in Git, not active dispatch.
