# XBrainLab Agent Benchmark v1 — visible pilot

This directory is the versioned source for the measurement-instrument pilot. It contains 12
human-authored semantic families with paired English and zh-TW variants (24 case records). Every
family belongs to `architecture_development`; this is not sealed thesis gold and must not be used
to report a final architecture effect.

Files:

- `corpus.json`: cases and canonical SHA-256 per case.
- `catalogs.json`: closed predicate, rubric, parameter-contract, and coverage vocabularies.
- `split_manifest.json`: family-level partition assignments.
- `schemas/`: case, corpus, run, trace, and verdict JSON interfaces.
- `examples/`: prerecorded normalized trace used to prove offline recomputation.

Validate the corpus:

```bash
poetry run python scripts/thesis/run_agent_benchmark.py
```

Recompute the checked-in example verdict:

```bash
poetry run python scripts/thesis/run_agent_benchmark.py \
  --trace benchmarks/xbrainlab_agent/v1/examples/pilot.scan-source.en.v1.trace.json
```

Generated artifacts belong under `build/dev-artifacts/thesis/agent-benchmark/` and are not benchmark
source. Shareable evidence must follow the privacy and claim-downgrade rules in
`docs/validation/thesis_protocol.md`.
