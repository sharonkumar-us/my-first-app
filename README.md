# Coverage Chatbot — Healthcare Insurance Q&A via RAG

A Kubernetes-deployed conversational AI system for insurance coverage questions, powered by retrieval-augmented generation (RAG), FastAPI, Streamlit, ChromaDB, and Ollama.

Status: Production-ready MVP with synthetic data. Compliance review needed before real member data.

Ranked 3rd in ABTalks 60-Day AI Challenge.

---

## What It Does

Ask the chatbot about your insurance coverage:
- Does my plan cover preventive care without a deductible?
- What's the status of my claim CLM-2024-987654?
- What if I need more physical therapy visits than my plan allows?

The chatbot retrieves relevant policy chunks, synthesizes an answer with the Ollama LLM, and traces every call to Langfuse for observability.

---

## Tech Stack

Backend: FastAPI, Ollama (local LLM), ChromaDB (vector DB), sentence-transformers
Frontend: Streamlit
Kubernetes: Minikube (dev) / EKS/GKE (prod)
Observability: Langfuse
Safety: Guardrails AI (output validation), custom PII redaction
Infrastructure: Docker, docker-compose, kubectl

---

## Getting Started

Prerequisites
- Docker Desktop
- Minikube (v1.38.1+)
- kubectl (v1.36+)
- Python 3.12+
- Ollama (running locally on port 11434)

Clone the Repo
git clone https://github.com/sharonkumar-us/my-first-app.git
cd my-first-app

Build and Deploy Locally
docker compose build
minikube start --driver=docker
minikube image load my-first-app-backend:latest
minikube image load my-first-app-frontend:latest
kubectl create secret generic ollama-secret --from-literal=OLLAMA_API_KEY=ollama
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/backend-service.yaml
kubectl apply -f k8s/frontend-deployment.yaml
kubectl apply -f k8s/frontend-service.yaml
kubectl get pods

Access the Frontend
kubectl get svc frontend
# Visit http://localhost:30501

Test the API
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"message": "Does my plan cover preventive care?", "plan_type": "PPO"}'

---

## Documentation

- capstone_walkthrough.md — 5 live scenario results + performance metrics
- retrospective.md — What worked, what was hard, what we'd do differently
- v2_roadmap.md — Multi-modal, voice, cloud K8s, compliance, ecosystem
- docker_notes.md — Container build decisions
- k8s_notes.md — Deployment and scaling lessons
- observability_notes.md — Langfuse tracing setup

---

## Key Features

RAG Pipeline — Hybrid retrieval with 94% accuracy on coverage Q's
Tool Calling — Deterministic router for claims lookup
Multi-Turn Memory — SQLite-backed conversation state
PII Redaction — Catches member names, DOB, claim IDs
Guardrails — Output validation to catch hallucinations
Health Probes — readinessProbe + livenessProbe for self-healing
Observability — Langfuse tracing on all LLM calls
Rate Limiting — 100 req/min per session
Caching — Exact-match query cache

---

## Deployment

Local (Development)
docker compose up
Backend on http://localhost:8000
Frontend on http://localhost:8501

Kubernetes (Production)
kubectl apply -f k8s/
Scales to 2 backend replicas, 1 frontend
Rolling updates with zero downtime

---

## Known Limitations

1. Synthetic Data Only — No real PHI
2. Ollama Local — No cloud LLM fallback
3. English-Only — No multilingual support
4. No Image Upload — Can't scan PDFs
5. Compliance Pending — Not HIPAA-certified yet

---

## Next Steps

1. Deploy to EKS/GKE (Q1 2027)
2. HIPAA Compliance Review (Q1 2027)
3. Multi-Modal + Voice (Q4 2026)
4. Ecosystem Integration (Q3-Q4 2027)

See v2_roadmap.md for full details.

---

## Built by

Sharon Kumar, Senior TPM at AWS
ABTalks 60-Day AI Challenge (Days 1-31 complete)
Leaderboard Rank: 3rd

This system is deployable, documented, and ready for production.
