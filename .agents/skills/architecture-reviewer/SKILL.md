# architecture-reviewer

## 用途

用於做 UI、backend、data pipeline、agent、validation 的架構複盤。

## 先讀

1. `docs/target/README.md`
2. `docs/target/architecture.md`
3. `docs/target/agent.md`
4. `docs/architecture/README.md`
5. `.agents/runbooks/architecture-review.md`

## 工作方式

1. 先描述 current implementation。
2. 再描述 target expectation。
3. 列出 gap。
4. 標出 risk。
5. 建議 first slice。
6. 寫出 required validation。

## 特別注意

- Backend 目前以 `Study` 為中心，UI 直接拿 controllers。
- `BackendFacade` 目前比較像 assistant / headless wrapper。
- target 是 Application Service / Command API，不是把所有邏輯塞進 facade。
- agent target 包含 State Manager、Verification Layer、capability policy、tool-call scoring。

## 禁止

- 不直接開始重構。
- 不把 target 當已完成。
- 不只看文件；需要對 source 或 tests。
