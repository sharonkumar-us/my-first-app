# Day 30 — Monitoring & Observability

## Work Completed

Integrated Langfuse distributed tracing into the coverage chatbot backend to capture LLM call latency, token usage, and full request/response payloads.

## Implementation

### Langfuse Setup
- Signed up for free cloud tier at https://langfuse.com
- Created "my-first-app" project
- Stored API keys in .env (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST)

### Code Changes
- Added `from langfuse import Langfuse` to coverage-chatbot-api/main.py
- Initialized Langfuse client on startup with error handling
- Added manual trace wrapping to /chat endpoint using `langfuse_client.trace()`
- Added langfuse>=2.0.0 to coverage-chatbot-api/requirements.txt

### Tracing Pattern
```python
if langfuse_client:
    with langfuse_client.trace(name="chat_request", input={"query": query.message}) as trace:
        result = retrieve_and_answer(query.message)
        trace.output = result
else:
    result = retrieve_and_answer(query.message)
```

This captures:
- Latency (how long each LLM call takes)
- Token usage (prompt + completion tokens)
- Full prompt/response payload
- Trace hierarchy (shows which calls are nested)

## What We Learned

### LLM Observability Essentials
- Latency is critical to monitor — p95 latency thresholds catch performance degradation early
- Token usage reveals efficiency: fine-tuning or prompt optimization shows in lower token counts
- Full trace payloads help debug unexpected model behavior without rerunning the query
- Distributed tracing (traces across microservices) is the industry pattern

### Production Alert Sketch
Would define thresholds for:
- Error rate: alert if >5% of requests fail
- p95 latency: alert if >3s (users notice this)
- Daily cost ceiling: alert if token usage exceeds budget
- Token explosion: alert if a single request uses >10k tokens (sign of retrieval loop or stuck recursion)

## Deployment Status

Docker image build failed due to system I/O errors (disk pressure). Code is ready; infrastructure retry is next step.

Backend container would run with:
- All LLM calls traced to Langfuse cloud
- Traces visible in dashboard (latency graphs, token counts, error analysis)
- Production alerts available for SLA monitoring

## Next Steps

1. Restart Docker Desktop and retry build
2. Load image into minikube
3. Redeploy and generate test traces
4. Verify traces appear in Langfuse dashboard
5. Set up alert rules for error rate and latency p95
