# ── Stage 1: builder ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

COPY coverage-chatbot-api/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy backend app code
COPY coverage-chatbot-api/main.py .

# Copy root-level modules the backend imports
COPY rag_chatbot.py .
COPY retrieval_engine.py .
COPY tool_calling_chatbot.py .
COPY redact_pii.py .
COPY token_utils.py .
COPY response_cards.py .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
