# Day 29 — Kubernetes Notes

## Deployment Summary

Deployed the coverage chatbot to a local Minikube cluster with:
- 2-3 backend replicas (FastAPI)
- 1 frontend replica (Streamlit)
- Services exposing both apps
- Secret for Ollama API key
- Health probes (readiness + liveness)
- Resource requests/limits

All pods reached Running/Ready state. Rolling updates and scaling worked cleanly.

## Key Issues & Fixes

### 1. Chroma Collection Not Found at Startup

Problem: retrieval_engine.py crashed at module import if the Chroma collection didn't exist. In the cluster, there was no persistent storage, so the database started empty.

Root Cause: Module-level assignment assumed the collection already existed.

Fix: Lazy-loaded the collection in retrieval_engine.py. Moved the get_collection() call into a function that creates an empty collection if it doesn't exist.

### 2. Scaling (2 to 3 replicas)

kubectl scale deployment backend --replicas=3

Result: New pod started, reached Running state in ~30 seconds, passed readiness probe within ~15 seconds. No downtime.

### 3. Health Probes

Both readiness and liveness probes polled /health every 5-10 seconds. All pods stabilized at Ready immediately after the first successful probe.

## Files Created

- k8s/backend-deployment.yaml - 2-3 replicas, probes, resource limits
- k8s/backend-service.yaml - ClusterIP, port 8000
- k8s/frontend-deployment.yaml - 1 replica, probes
- k8s/frontend-service.yaml - NodePort 30501
