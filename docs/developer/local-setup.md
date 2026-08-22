# 本機開發環境

## 需求

- Python 3.11 或 3.12
- Poetry
- Git
- Qt、MNE、PyTorch 與本次要使用的 dataset reader 所需平台函式庫

選用的本機 Assistant 需要較多相依套件與儲存空間。只有任務涉及 Assistant runtime 時才安裝。

## 安裝相依套件

在 repository root 執行：

```bash
poetry install
```

需要本機 LLM 時加入對應 dependency group：

```bash
poetry install --with llm
```

不得隱式下載或替換模型。模型 identity、license、quantization、cache 位置與容量上限都屬於產品
決策。

## 啟動應用程式

```bash
poetry run python run.py
```

Repository root 的 `settings.json` 保存本機 runtime 設定，不屬於 feature change，必須維持
uncommitted。

## 驗證環境

安裝完成後，不要從完整 regression 開始。到[測試與驗證](testing.md)選擇與預計修改區域相符的
focused test 或 domain runner；該頁也說明 Qt／MNE／PyTorch、文件網站與本機 Granite 的執行條件。

## 產生檔與本機資料

- 開發 artifact 放在 ignored `build/dev-artifacts/`。
- 最終 handoff evidence 放在 ignored `build/handoff-evidence/<full-SHA>/`。
- Dataset storage、model／RAG cache、training output 與 evidence 各有獨立 owner。
- 不提交 cache、本機 dataset、臨時 screenshot 或複製的 runtime output。

把任何產生物解讀成 evidence 前，先閱讀[驗證契約](../validation/README.md)。
