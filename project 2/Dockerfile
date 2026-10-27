FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir "torch>=2.6,<3" --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY data/processed ./data/processed
COPY src ./src

ENV PYTHONUNBUFFERED=1
ENV GENERATION_PROVIDER=ollama
ENV OLLAMA_URL=http://host.docker.internal:11434
ENV ALLOW_PAID_CALLS=false
ARG APP_REVISION=unknown
ENV APP_REVISION=$APP_REVISION

EXPOSE 8000

CMD ["sh", "-c", "uvicorn api.app:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000}"]
