FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir "torch>=2.6,<3" --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

ARG EMBEDDING_REVISION=e8f8c211226b894fcb81acc59f3b34ba3efd5f42
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', revision='$EMBEDDING_REVISION').save('/opt/models/minilm')" \
    && rm -rf /root/.cache/huggingface

COPY data/processed ./data/processed
COPY config ./config
COPY src ./src

ENV PYTHONUNBUFFERED=1
ENV EMBEDDING_MODEL=/opt/models/minilm
ENV EMBEDDING_REVISION=$EMBEDDING_REVISION
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
ENV GENERATION_PROVIDER=ollama
ENV OLLAMA_URL=http://host.docker.internal:11434
ENV ALLOW_PAID_CALLS=false
ARG APP_REVISION=unknown
ENV APP_REVISION=$APP_REVISION

RUN useradd --uid 10001 --create-home librarian \
    && mkdir /state && chown librarian:librarian /state \
    && chmod -R a+rX /opt/models
USER librarian

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health', timeout=4)"

CMD ["sh", "-c", "exec uvicorn api.app:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000}"]
