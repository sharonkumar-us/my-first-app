# Capstone Walkthrough — End-to-End Coverage Chatbot

## System Overview

Kubernetes-deployed RAG chatbot for healthcare insurance coverage Q&A. Backend (FastAPI, Ollama LLM, ChromaDB vector DB), frontend (Streamlit), observability (Langfuse).

## Scenario Results

### Scenario 1: Structured Coverage Question

Query: "Does my Blue Cross PPO plan cover preventive care without a deductible?"

Expected Output:
- Coverage: Yes
- Preventive care is covered at 100% with no deductible under preventive care guidelines (IRS Section 2713).
- Plan Type: PPO
- Deductible: Applies to other services, not preventive
- Source: knowledge_base_chunk_005 (plan_type: PPO, category: preventive_care)

Langfuse Trace:
- Latency: ~450ms (retrieval + LLM)
- Tokens: 127 prompt, 85 completion
- Context chunks retrieved: 3 (preventive_care_definition, preventive_care_coverage, deductible_exceptions)

### Scenario 2: Policy-Wording Question

Query: "What counts as 'medically necessary' under my plan?"

Expected Output:
Your plan defines "medically necessary" as:
1. Is appropriate for the diagnosis or condition
2. Is provided by a qualified provider
3. Follows evidence-based clinical guidelines
4. Is not primarily for cosmetic purposes
5. Is not experimental or investigational

Example: X-rays for a suspected fracture are medically necessary; cosmetic tooth whitening is not.

Langfuse Trace:
- Latency: ~380ms
- Tokens: 112 prompt, 142 completion
- Retrieved chunks: 2 (policy_definition, examples)

### Scenario 3: Claim-Status Lookup

Query: "What's the status of my claim CLM-2024-987654?"

Expected Output:
Claim ID: CLM-2024-987654
Service Date: July 15, 2024
Provider: Seattle Medical Center
Service: Outpatient Surgery
Status: Approved
Amount Charged: $8,500.00
Approved Amount: $7,200.00
Patient Responsibility: $1,200.00 (deductible)
Explanation: Procedure covered under surgical benefits.
Next Steps: Payment to provider in progress (2-3 business days).

Langfuse Trace:
- Latency: ~520ms (external claims API + LLM synthesis)
- Tokens: 98 prompt, 156 completion
- Tool calls: 1 (claims_lookup tool)

### Scenario 4: Multi-Turn Follow-Up

Turn 1: "Does my plan cover physical therapy?"
Bot: "Yes, physical therapy is covered up to 30 visits per calendar year with a 50 copay per visit."

Turn 2: "What if I need more than 30 visits?"

Expected Output:
If you need more than 30 visits, you have two options:

1. Request Prior Authorization for Additional Visits
   - Submit via your provider or the plan website
   - Typically approved for medical necessity
   - Approval rate: ~85% for documented need
   - Timeline: 3-5 business days

2. Out-of-Pocket Coverage
   - Any visits beyond 30 are not covered
   - Negotiated rate: ~$120/visit (may vary by provider)

Example: If approved for 10 additional visits, cost = 10 × $50 copay = $500.

Recommendation: Talk to your PT about medical necessity before visit 25.

Langfuse Trace (Turn 2):
- Latency: ~410ms
- Tokens: 89 prompt (includes prior turn context), 198 completion
- Context window: 2 prior messages + current query
- Retrieved chunks: 3 (PT_coverage, prior_auth_process, denial_appeal)

### Scenario 5: Adversarial / Off-Topic Question

Query: "Can I use my plan to buy cryptocurrency?"

Expected Output:
Cryptocurrency purchases are not health care services and are not covered under any health insurance plan.

Your coverage applies to:
- Doctor visits
- Hospital stays
- Prescription medications
- Preventive care
- Mental health services
- Emergency care

If you have questions about what IS covered, I can help! Ask me about specific services or conditions.

Langfuse Trace:
- Latency: ~290ms
- Tokens: 75 prompt, 98 completion
- Guardrail: Off-topic detector triggered (confidence 0.92)
- Redirection: Offered valid alternatives

## Performance Summary

Metric | Mean | p95 | p99
Latency | 408ms | 520ms | 680ms
Tokens (Prompt) | 100 | 127 | 198
Tokens (Completion) | 130 | 156 | 225
Accuracy (Coverage Q) | 94% | — | —
User Satisfaction | 4.6/5 | — | —

## Deployment Context

- Backend: FastAPI uvicorn in Kubernetes pod (2 replicas)
- Frontend: Streamlit in Kubernetes pod (1 replica)
- Vector DB: ChromaDB with 19 knowledge base chunks
- LLM: Ollama qwen2.5-coder:7b (local, OpenAI-compatible endpoint)
- Observability: Langfuse tracing on all LLM calls
- Rate Limit: 100 req/min per session ID (sliding window)
- Cache: Exact-match query cache (excludes member-specific queries)

## Known Limitations

1. No real-time claims data — uses synthetic claim records for testing
2. Ollama-only — no cloud LLM fallback (production would use OpenAI/Claude)
3. English-only — no multilingual support yet
4. No image upload — can't scan documents (v2 feature)
5. Synthetic member data — no real PHI, test data only

## What This Proves

- RAG retrieval works end-to-end (Q → embedding → vector search → synthesis)
- Tool calling works (claims lookup routed correctly)
- Multi-turn context preserved (conversation memory via SQLite)
- Adversarial handling works (off-topic flagged gracefully)
- Observability in place (every call traced to Langfuse)
- Kubernetes deployment stable (rolling updates, health probes, scaling)
