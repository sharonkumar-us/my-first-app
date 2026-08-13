# Day 28 — Docker Notes

## Stack

- Backend: FastAPI (multi-stage Dockerfile, coverage-chatbot-api/Dockerfile)
- Frontend: Streamlit (Dockerfile.frontend)
- Orchestration: docker-compose.yml at repo root
- Chroma data: bind-mounted from ./chroma_data (populated locally, persists across restarts)
- Secrets: passed via .env (gitignored); .env.example committed as template

## Build command

docker compose up --build

Both images built successfully:
- my-first-app-backend: multi-stage, Python 3.12-slim, deps installed in builder stage
- my-first-app-frontend: single-stage, Python 3.12-slim, Streamlit only

## Issues resolved during build

1. requirements.txt only had fastapi + uvicorn (Day 3 skeleton) - updated to include all
   runtime deps: openai, python-dotenv, pydantic, sentence-transformers, chromadb, ollama, tiktoken
2. Root-level modules (rag_chatbot.py, retrieval_engine.py, etc.) were outside the original
   build context - fixed by setting build context to repo root and copying modules explicitly
3. Chroma named volume was empty on first run - switched to bind mount (./chroma_data) so
   the pre-populated collection is available inside the container

## Health check proof

curl http://localhost:8000/health returned: {"status":"ok"}

docker ps output:
CONTAINER ID   IMAGE                   STATUS
8d8eec9411b5   my-first-app-frontend   Up (healthy)
e7a9abf56ccb   my-first-app-backend    Up (healthy)

Both services healthy. /health responds from inside the container network.
HEALTHCHECK instruction in backend Dockerfile polls /health every 30s.

## Design decisions

- host.docker.internal used as Ollama base URL so container reaches host Ollama
- depends_on: condition: service_healthy ensures frontend starts only after backend is healthy
- Bind mount used for local dev; named volume kept in compose for clean-slate deployments
