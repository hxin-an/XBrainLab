import os
from sentence_transformers import SentenceTransformer, util
from typing import List, Tuple
import torch

class RAGEngine:
    """
    Retrieval-Augmented Generation (RAG) Engine.
    
    Responsible for:
    1. Loading reference documents.
    2. splitting text into chunks.
    3. Encoding documents into embeddings.
    4. Retrieving relevant context based on queries.
    """

    def __init__(self, model_name: str = 'sentence-transformers/all-mpnet-base-v2', device: str = None):
        """
        Initialize the RAG Engine.

        Args:
            model_name (str): The name of the SentenceTransformer model to use.
            device (str): Device to run the model on ('cpu', 'cuda', or None for auto).
        """
        self.device = device
        if self.device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        print(f"[RAGEngine] Loading retriever model: {model_name} on {self.device}")
        self.retriever = SentenceTransformer(model_name, device=self.device)
        
        self.documents: List[Tuple[str, str]] = []  # List of (chunk_id, chunk_text)
        self.document_embeddings = None

    def split_text_into_chunks(self, text: str, chunk_size: int = 512) -> List[str]:
        """
        Split a long text into smaller chunks for embedding.

        Args:
            text (str): The input text.
            chunk_size (int): The maximum size of each chunk.

        Returns:
            List[str]: A list of text chunks.
        """
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    def load_reference_document(self, path: str, chunk_size: int = 512) -> None:
        """
        Load a reference document, chunk it, and compute embeddings.

        Args:
            path (str): Path to the text file.
            chunk_size (int): Size of chunks.
        """
        if not os.path.exists(path):
            print(f"[RAGEngine] Warning: Reference file not found at {path}")
            return

        print(f"[RAGEngine] Loading reference document from {path}")
        with open(path, 'r', encoding='utf-8') as file:
            doc = file.read()
            chunks = self.split_text_into_chunks(doc, chunk_size)
            
            start_idx = len(self.documents)
            for idx, chunk in enumerate(chunks):
                self.documents.append((f"chunk_{start_idx + idx}", chunk))
        
        # Re-compute embeddings for all documents
        # Optimization: In a production system, we might want to incrementally update or cache this.
        self._update_embeddings()

    def _update_embeddings(self) -> None:
        """Compute embeddings for all currently loaded documents."""
        if not self.documents:
            self.document_embeddings = None
            return
            
        texts = [chunk[1] for chunk in self.documents]
        print(f"[RAGEngine] Encoding {len(texts)} chunks...")
        self.document_embeddings = self.retriever.encode(texts, convert_to_tensor=True)

    def retrieve(self, query: str, top_k: int = 3) -> List[str]:
        """
        Retrieve the most relevant document chunks for a given query.

        Args:
            query (str): The user's input query.
            top_k (int): Number of chunks to retrieve.

        Returns:
            List[str]: A list of relevant text chunks.
        """
        if self.document_embeddings is None or len(self.documents) == 0:
            return []

        query_embedding = self.retriever.encode(query, convert_to_tensor=True)
        hits = util.semantic_search(query_embedding, self.document_embeddings, top_k=top_k)
        
        # hits structure: [[{'corpus_id': int, 'score': float}, ...]]
        relevant_chunks = [self.documents[h['corpus_id']][1] for h in hits[0]]
        return relevant_chunks

    def encode(self, texts: List[str], convert_to_tensor: bool = True):
        """Helper to encode texts directly (used by Prompt Selector)."""
        return self.retriever.encode(texts, convert_to_tensor=convert_to_tensor)
