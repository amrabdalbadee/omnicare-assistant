FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Warm the local embedding model into the image so the first request after
# `docker-compose up` is fast and the container needs no network for
# retrieval. Non-fatal: if the download is unavailable at build time the
# service falls back to lexical retrieval at runtime.
RUN python -c "\
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; \
DefaultEmbeddingFunction()(['warm up the embedding model'])" || \
    echo 'Embedding model not pre-cached; will download on first use.'

COPY app ./app
COPY tests ./tests
COPY pytest.ini .

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=40s --retries=5 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
