# ba-rag-vectordb-benchmark

Dieses Repository enthält die Artefakte zur Reproduktion eines Benchmarks für **Retrieval-Augmented Generation (RAG)** in **Open WebUI**. Verglichen werden verschiedene Vector-DB-Backends (**ChromaDB, pgvector, Elasticsearch, Qdrant**) sowie eine **No-RAG (LLM-only)** Baseline.

## Start

Wähle ein Backend und starte den Stack (Beispiel: ChromaDB):

```bash
docker compose -f docker-compose.chromadb.yaml up -d
