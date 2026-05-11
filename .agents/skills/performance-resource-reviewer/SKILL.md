---
name: performance-resource-reviewer
description: Use when reviewing XBrainLab performance, memory, GPU/VRAM, model cache, long-running jobs, PyQt responsiveness, WSL stability, dataset scan cost, and whether native code or optimization is justified.
---

# performance-resource-reviewer

## 用途

用於檢查 XBrainLab 是否會卡 UI、炸 WSL、爆 VRAM / disk，或用錯優化方向。

## 設計來源

已消化參考：

- PyTorch CUDA docs：GPU memory 有 caching allocator；需要區分 allocated / reserved / cached，
  並可用工具觀察 CUDA memory。
- Qt thread / QObject docs：GUI thread、QObject thread affinity、worker thread、signal/slot
  邊界必須清楚，不能跨 thread 直接碰 UI。
- XBrainLab 現況：local LLM、training、saliency、PyVista/Matplotlib、BIDS scan、MNE/PyTorch
  都可能是長任務或高記憶體操作。

## 先讀

1. `docs/current.md`
2. `docs/architecture/ui.md`
3. `docs/architecture/backend.md`
4. `docs/validation/README.md`
5. touched long-running / GPU / UI / data-scan code

## Review Gate

檢查：

- 是否先 profile / measure，再討論 C++ / Rust / CUDA 重寫。
- 熱點是否真的在 Python loop，而不是 MNE / NumPy / PyTorch / IO / GPU kernel。
- UI thread 是否只做 UI；data scan、training、local model、visualization render 是否有 worker/job boundary。
- long-running command 是否有 progress、cancel、timeout、state recovery。
- local model 下載是否有 disk / VRAM preflight、cache cap、no-China policy。
- GPU memory 是否有 predictable failure message，不讓 WSL/Codex 卡死。
- dataset scan / BIDS import 是否避免無界遞迴、巨大檔案同步讀、重複解析。
- native sidecar 是否有清楚 boundary、測試、fallback、build story；不為了速度把部署弄壞。

## 打回條件

- 沒有 profiling 就大改 Rust/C++。
- long-running job 阻塞 UI event loop。
- model download / training 沒有 resource preflight。
- memory failure 只出 traceback，沒有 recoverable user message。
- WSL 卡死後沒有縮小 test profile 或 timeout。

## 輸出格式

```md
## Resource Verdict

- verdict: safe / watch / unsafe

## Bottleneck Evidence

## UI Responsiveness

## GPU / Disk / Memory

## Optimization Recommendation
```
