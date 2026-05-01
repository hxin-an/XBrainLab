# refactor-slicer

## 用途

用於把後端 / agent 重構切成可驗證的小 slice。

## 先讀

1. `.agents/runbooks/refactor-gate.md`
2. `docs/target/architecture.md`
3. `docs/architecture/backend.md`
4. `docs/validation/README.md`

## Slice 格式

每個 slice 必須寫：

- scope
- current call sites
- target command shape
- affected files
- validation plan
- non-goals
- rollback / shrink plan

## 選 slice 原則

- 優先選低風險 workflow。
- 優先建立 Application Service / Command API 的薄切片。
- 先保護 current behavior，再改入口。
- 不同時大改 UI、backend、agent tools、runtime。

## 禁止

- 不在未盤點 call sites 前改 controller。
- 不只靠 MagicMock 保護 real side effect。
- 不讓 agent tools 直接綁零散 controller internals。
