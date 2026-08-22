# XBrainLab Now

最後更新：`2026-08-22`

## 目前焦點

`ci/native-platform-reliability-v1` 已由 PR #44 在 exact head
`a679f1417649f4266a2af84809684e40b2109293` 完成 applicable CI 與使用者 Windows／Linux 手測，並以
merge commit `8d8dcf6030d0b4bd79783b3a086e1efa101d0cd2` 合併至 `main`。

`research/xbrainlab-agent-benchmark-v1` 的 measurement-instrument 第一切片已 scope-complete：正式文獻探索與
方法推導、canonical thesis protocol、五個 versioned schemas、12 個人工 pilot semantic families／24 個
雙語 paired variants、fail-closed corpus validator、deterministic four-layer episode scorer、prerecorded
trace、create-only verdict artifact與真 ApplicationService privacy-bounded observation seam均已落地。

本切片沒有下載或執行 local model、沒有復跑 2025 legacy runtime、沒有建立 sealed gold、沒有比較 agent
architecture，也沒有 accuracy／superiority／power／ablation result。這些缺口不能由 Stable 50-case產品gate、
deterministic replay或文件完整度替代。

目前沒有 active implementation slice。下一個候選是獨立 branch 的 legacy/current adapters與 visible
development pilot；開始前須另行更新本文件，先完成 legacy RAG corpus redistribution/license決策、model
source/revision/resource preflight與 adapter equivalence tests。之後的 model screening＋dataset freeze、
architecture iteration＋sealed comparison＋ablation仍各自拆 slice，不在未凍結 evidence contract前合併施工。

## Canonical authority

- 研究證據與方案推導：`docs/research/xbrainlab_agent_benchmark_methodology.md`。
- Benchmark claim、partition、scoring、statistics、sealing與 downgrade contract：
  `docs/validation/thesis_protocol.md`。
- Versioned source inputs：`benchmarks/xbrainlab_agent/v1/`。
- Research-only implementation：`XBrainLab/experiments/agent_benchmark/`與
  `scripts/thesis/run_agent_benchmark.py`。

Product `ApplicationService / Command API`仍是唯一 state、capability、confirmation與 mutation owner；
benchmark harness只驗證source contract、重算 normalized trace並產出immutable verdict。Root `settings.json`
保持使用者本機設定，不屬任何研究 slice。
