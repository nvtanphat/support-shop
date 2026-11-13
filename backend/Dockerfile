FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast Python dependency management
COPY --from=ghcr.io/astral-sh/uv:0.5.10 /uv /uvx /bin/

# Copy dependency definition
COPY pyproject.toml /app/

# Install dependencies into system environment
# The `rerank` extra (fastembed) serves policy lookups: the reranker and the embedding model in config/app.yaml.
RUN uv pip install --system -r pyproject.toml --extra rerank

# Bake the models into the image so the first policy lookup does not download them:
# the cross-encoder (570 MB) and the int8 BGE-M3 embedding model (570 MB, retrieval.embedding in config/app.yaml).
ENV FASTEMBED_CACHE_PATH=/models
RUN python -c "from fastembed.rerank.cross_encoder import TextCrossEncoder; TextCrossEncoder(model_name='BAAI/bge-reranker-v2-m3-int8')"
COPY src/shopagent/rag/bge_m3.py /tmp/bge_m3.py
RUN cd /tmp && python -c "import bge_m3; bge_m3.prefetch()" && rm /tmp/bge_m3.py

# Copy source code and config
COPY src/ /app/src/
COPY config/ /app/config/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "shopagent.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
