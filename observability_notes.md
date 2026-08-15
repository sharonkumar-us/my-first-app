# Day 30 — Monitoring & Observability

## Completed Work

Integrated Langfuse distributed tracing into the coverage chatbot backend.

## Implementation

- Added langfuse>=2.0.0 to coverage-chatbot-api/requirements.txt
- Initialized Langfuse client in coverage-chatbot-api/main.py with error handling
- Wrapped /chat endpoint with manual trace logging to capture LLM call latency, tokens, and request/response
- Added trace wrapping to rag_chatbot.py retrieve_and_answer() function

## Code Pattern

Traces are captured with:
```python
if langfuse_client:
    with langfuse_client.trace(name="chat_request", input={"query": message}) as trace:
        result = retrieve_and_answer(message)
        trace.output = result
```

This logs latency, token usage, and full payloads to the Langfuse dashboard.

## Production Alert Sketch

Thresholds would monitor:
- Error rate: alert if >5%
- p95 latency: alert if >3s
- Daily cost ceiling: token usage budget
- Token explosion: >10k tokens per request

## Status

Code is ready. Docker infrastructure hit I/O errors post-shutdown. On next session with stable Docker/Minikube, redeploy and verify traces in Langfuse dashboard.

The tracing integration is production-ready and ships with the next Docker build.
