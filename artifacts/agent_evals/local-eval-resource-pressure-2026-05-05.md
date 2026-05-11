# XBrainLab Local Eval Resource Pressure

- date: `2026-05-05`
- gate type: `release/thesis local tool-call evidence`
- command: `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role fallback --repeat-count 3 --output-dir artifacts/agent_evals/local_fallback`
- model: `microsoft/Phi-3.5-mini-instruct`
- result: `121 / 121`, repeat count `3`
- artifact: `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.json`

## Resource Notes

Preflight found both primary and fallback models already cached, estimated download `0.00 GB`,
model cache usage `15.34 GB`, cache limit `20.00 GB`, and free disk about `158.36 GB`.

During the fallback x3 run, `nvidia-smi` showed RTX 5070 Ti VRAM near the 16 GB boundary:

| Time | VRAM Used | VRAM Free | GPU Util | Process Elapsed | Process RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| `2026-05-05 22:10:33 CST` | `15764 MiB` | `232 MiB` | `99%` | `38:40` | `2330376 KB` |

After the run completed, `nvidia-smi` showed `1026 MiB` used, `14970 MiB` free, and `8%` GPU
utilization.

Approximate fallback wall time was about `41 min`. This is high resource pressure on a 16 GB VRAM
GPU and should not be used as a default dev gate.

## Gate Boundary

- Fast dev gate: deterministic eval, changed or failed cases only, repeat `1`, no fallback model.
- Candidate gate: primary model, affected case families, repeat `1` or `2`.
- Release / thesis gate: deterministic full suite, primary full suite x3, fallback full suite x3,
  dashboard refresh, with resource pressure recorded.
