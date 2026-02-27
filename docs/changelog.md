# Changelog

詳見 [完整變更紀錄](../documentation/CHANGELOG.md)。

## [0.5.4] - Latest

### Added
- **TrainingManager** — 從 Study 抽取訓練生命週期管理
- **AgentMetricsTracker** — 結構化日誌、Token 追蹤、工具執行記錄
- **VerificationLayer Validators** — Pluggable 驗證策略 (Frequency, Training, Path)
- **E2E Pipeline Tests** — 26 個端對端測試
- **MkDocs Documentation** — API 文檔自動生成

### Refactored
- **BasePanel Bridge** — `_create_bridge()` 統一 Observer 橋接模式

### Quality
| 指標 | 狀態 |
|---|---|
| Ruff | 0 errors |
| Mypy | 0 errors |
| Tests | 3879 passed |
| Coverage | ~92% |

## [0.5.3]

- 全專案 199 項 Code Review 修復
- ContextAssembler + VerificationLayer 整合
- CI/CD Pipeline (GitHub Actions)
- 執行緒安全修復 (threading.Event)
- Logger f-string → lazy formatting (89 處)

## [0.5.2]

- Real Tool Testing Platform
- Montage 前後端分離
- 3D Visualization 修復

## [0.5.1]

- Chat Panel Copilot 風格重設計
- Observer Bridge 系統建立
