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
RUN uv pip install --system -r pyproject.toml

# Copy source code and config
COPY src/ /app/src/
COPY config/ /app/config/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "shopagent.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
