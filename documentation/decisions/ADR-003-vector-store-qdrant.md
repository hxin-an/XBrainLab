# ADR-003: 向量資料庫選型 - Qdrant (Vector Store Selection)

## 背景 (Context)
在確立了 **ADR-001 (混合模式)** 與 **ADR-002 (虛擬多 Agent)** 後，我們需要為 Phase 4 (RAG) 選擇一個具體的向量資料庫 (Vector Database)。
使用者明確指定使用 **Qdrant**。

## 選型分析 (Analysis)

### 1. 為什麼選擇 Qdrant？
*   **效能 (Performance)**: 基於 **Rust** 編寫，查詢速度極快，記憶體管理優異。
*   **部署彈性 (Deployment)**: 
    *   **Local Mode (On-disk)**: 這是我們最需要的模式。不需要 Docker，不需要 Server，只需 `pip install qdrant-client`，即可直接將向量存儲在本地檔案系統 (`/path/to/storage`)。
    *   **Server Mode**: 未來若需擴展，可無縫遷移至 Docker/Cloud 版本。
*   **LangChain 整合**: `langchain-qdrant` 提供了成熟的整合，支援 Filter 搜尋 (Metadata Filtering)，這對我們的「分析師 Agent」(需要根據檔案類型過濾) 非常重要。

### 2. 與其他方案比較
*   **vs Chroma**: Chroma 也很易用，但穩定性與大數據量下的效能不如 Qdrant。
*   **vs FAISS**: FAISS 是底層庫，缺乏高階的 CRUD 與 Metadata Filter 管理功能，Qdrant 使用體驗更佳。

## 決策 (Decision)
我們將使用 **Qdrant** 作為唯一的向量資料庫。

### 實作細節
*   **套件依賴**: 新增 `qdrant-client` 與 `langchain-qdrant`。
*   **儲存規劃**: 向量資料將儲存在 `XBrainLab/llm/rag/knowledge_base/qdrant_storage` 目錄下 (需添加到 `.gitignore`)。
*   **混合檢索 (Hybrid Search)**: Qdrant 支援 Sparse/Dense 混合檢索，保留未來擴充關鍵字搜尋的能力。

## 下一步 (Next Steps)
1.  更新 `pyproject.toml` 加入 Qdrant 相關依賴。
2.  在 Phase 4 實作 `RAGEngine` 時，初始化 Qdrant Client 指向本地路徑。
