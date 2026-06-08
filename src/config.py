import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "docs")

EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "gpt-4o-mini"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

# Hybrid search: weight given to dense (semantic) vs sparse (BM25) scores
# before reranking. 1.0 = pure semantic, 0.0 = pure keyword.
DENSE_WEIGHT = 0.6

RETRIEVAL_TOP_K = 20      # candidates pulled from each retriever before fusion
RERANK_TOP_K = 5          # final passages handed to the generator after reranking
