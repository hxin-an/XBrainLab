import contextlib
import logging
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from XBrainLab.llm.rag import RAGIndexer, RAGRetriever

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RAGVerify")


def main():
    print("=== RAG Verification Script ===")

    # Path to gold set
    gold_set_path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__), "../XBrainLab/llm/rag/data/gold_set.json"
        )
    )

    if not os.path.exists(gold_set_path):
        print(f"Error: Gold set not found at {gold_set_path}")
        return

    # 1. Indexing
    print(f"\n[1] Indexing Gold Set from {gold_set_path}...")
    indexer = RAGIndexer()
    docs = indexer.load_gold_set(gold_set_path)
    indexer.index_data(docs)
    print(f"Indexed {len(docs)} documents.")

    # Close indexer to release lock
    if hasattr(indexer, "client"):
        with contextlib.suppress(AttributeError):
            indexer.client.close()
    del indexer

    # 2. Retrieval
    print("\n[2] Testing Retrieval...")
    retriever = RAGRetriever()

    test_queries = [
        "Load data from /tmp/data",
        "Filter data 1Hz to 50Hz",
        "Start training with EEGNet",
        "Attach labels mappings to the file",
    ]

    for query in test_queries:
        print(f"\nQuery: '{query}'")
        result = retriever.get_similar_examples(query, k=1)
        print("-" * 40)
        print(result.strip())
        print("-" * 40)

    print("\n=== Verification Complete ===")


if __name__ == "__main__":
    main()
