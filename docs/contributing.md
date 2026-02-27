# Contributing

## 開發環境設置

```bash
git clone https://github.com/your-org/XBrainLab.git
cd XBrainLab
poetry install --with dev,docs
```

## 開發規範

### 程式碼品質
- **Linting**: `poetry run ruff check XBrainLab/ tests/`
- **Type Check**: `poetry run mypy XBrainLab/`
- **Format**: `poetry run ruff format XBrainLab/ tests/`
- **Pre-commit**: 自動執行 ruff、mypy、secrets 掃描

### 測試
- **執行測試**: `poetry run pytest tests/ --deselect tests/unit/ui/test_visualization.py::TestSaliency3DEngine -q`
- **覆蓋率**: `poetry run pytest --cov=XBrainLab --cov-report=html`
- 新功能必須附帶對應的單元測試
- 整合測試放在 `tests/integration/`

### 架構原則
1. **Backend Headless**: Backend 不依賴 PyQt6
2. **Observer 解耦**: Controller 透過 `Observable.notify()` 通知 UI
3. **Facade Pattern**: Agent/Script 透過 `BackendFacade` 操作後端
4. **Property Delegation**: Study 委派至 DataManager + TrainingManager
5. **Bridge Pattern**: Panel 使用 `_create_bridge()` 建立 Observer 橋接

### 提交規範
使用 Conventional Commits：
- `feat:` 新功能
- `fix:` Bug 修復
- `refactor:` 重構
- `test:` 測試
- `docs:` 文檔

詳見 [CONTRIBUTING.md](../documentation/CONTRIBUTING.md)。
