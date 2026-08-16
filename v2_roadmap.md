# V2 Roadmap — Prioritized Next Features

## Phase 1: Core Capability Expansion (Q4 2026 — Q1 2027)

### 1.1 Multi-Modal Support (High Priority, High Impact)

Problem: Insurance documents are PDFs. Scanning claims statements manually is tedious.

Solution:
- Add image/PDF upload to Streamlit frontend
- Use OCR (Tesseract or cloud Vision API) to extract text from scanned documents
- Feed extracted text + images into retrieval pipeline

Effort: 2 weeks (OCR integration + prompt engineering for image context)
Risk: OCR accuracy varies by document quality; scanned forms need template recognition
Success Metric: >90% text extraction accuracy on test claims forms

### 1.2 Voice Input/Output (Medium Priority, High Delight)

Problem: Text typing on mobile is friction. Voice is natural for questions.

Solution:
- Add speech-to-text (Whisper API or browser Web Speech API)
- Add text-to-speech output (gTTS or AWS Polly)
- Stream audio responses for smooth UX

Effort: 1 week
Risk: Accent/dialect bias in STT; latency on TTS
Success Metric: 80%+ STT accuracy on US English accents; <800ms TTS latency

### 1.3 Multi-Language Support (Medium Priority, Medium Effort)

Problem: Healthcare users in the US speak English, Spanish, Mandarin, etc.

Solution:
- Detect user language via browser locale or explicit picker
- Translate knowledge base chunks to target language on first load
- Translate user queries to English for retrieval, translate responses back

Effort: 2 weeks (translation API integration + prompt engineering for clinical accuracy)
Risk: Medical terminology doesn't always translate; context loss in translation
Success Metric: Parity with English on coverage Q accuracy for top 5 languages

## Phase 2: Production Readiness (Q1 2027 — Q2 2027)

### 2.1 Cloud Kubernetes Deployment (High Priority, High Effort)

Current: Minikube on local dev machine
Target: EKS or GKE with auto-scaling

Why: 
- Minikube doesn't handle persistent storage well (we learned this the hard way)
- Cloud K8s provides managed database, auto-scaling, high availability
- Production SLA requires 99.9% uptime; local laptop can't deliver that

Effort: 3 weeks (infrastructure setup, CI/CD pipeline, load testing)
Components:
- AWS EKS or Google GKE cluster (managed control plane)
- Cloud SQL (PostgreSQL) for conversation state (replaces SQLite in pod)
- Managed vector DB (AWS Bedrock Knowledge Base or Pinecone) (replaces ChromaDB)
- Cloud logging (CloudWatch or Stackdriver)
- Auto-scaling based on CPU/memory metrics

Success Metric: Pod 99.9% uptime SLA; <5 min deploy time

### 2.2 Formal Compliance & Legal Review (High Priority, Moderate Effort)

Current: Synthetic data, no real PHI
Target: HIPAA-grade audit ready

Why: If this goes to production with real member data, compliance is mandatory

What's needed:
- HIPAA Business Associate Agreement (BAA) with Langfuse
- Data encryption at rest (AES-256) and in transit (TLS 1.3)
- Audit logging (who accessed what, when, why)
- Data retention policy (delete member data after X days if not requested)
- Legal review: terms of service, privacy policy, data handling procedures
- Penetration testing / security audit

Effort: 4 weeks (legal + infra work)
Success Metric: HIPAA compliance certification; SOC 2 Type II audit readiness

### 2.3 API Gateway & Rate Limiting (Medium Priority, Low Effort)

Current: Direct FastAPI endpoint, basic sliding-window rate limiter
Target: API Gateway (Kong or AWS API Gateway) with quota/throttling per client

Why: If external partners integrate, need fair usage + billing metering

Effort: 1 week
Success Metric: Support up to 5 concurrent integrations with independent rate limits

## Phase 3: Intelligence & Personalization (Q2 2027 — Q3 2027)

### 3.1 Personalized Coverage Summaries (Medium Priority, Medium Effort)

Current: Generic answers ("your plan covers X")
Target: Member-specific summaries based on prior questions

Example:
- Member asks about PT coverage → system remembers this
- Member asks about preventive care → system flags "you asked about PT; note that PT is also preventive"

Effort: 2 weeks (user profile store + context injection into prompts)
Success Metric: 70% of follow-up Q's reference prior context without user restating it

### 3.2 Proactive Alerts (Low Priority, Medium Effort)

Problem: Member doesn't know coverage changes until they hit a bill

Solution:
- Digest plan change notifications (policy updates, network changes)
- Alert members: "Your out-of-network copay increased from $50 to $75"
- Integrate with member calendar/SMS for delivery

Effort: 3 weeks
Success Metric: 50% engagement on alerts; NPS +5 points

### 3.3 Claims Prediction & Appeal Guidance (Medium Priority, High Effort)

Current: Claim status lookup only
Target: Predict claim approval + suggest appeal path if denied

Example:
- Member uploads claim → system predicts ~70% approval odds
- If denied → system suggests appeal strategy based on policy language + similar claims

Effort: 4 weeks (ML model for approval prediction + appeals knowledge base)
Risk: Predictions could be wrong; legal liability if guidance is inaccurate
Success Metric: Prediction accuracy >80%; 30% of appeals result in reversal

## Phase 4: Ecosystem Integration (Q3 2027 — Q4 2027)

### 4.1 Electronic Health Record (EHR) Integration

Problem: Data silos. Doctors have records; insurance has separate records.

Solution: HL7 FHIR API integration with Epic, Cerner, Athena (major EHR platforms)
Benefit: Member history available to chatbot; drug interactions checked against active meds

Effort: 6 weeks (FHIR standard learning + authentication + testing)
Risk: High — HIPAA violation if data not handled correctly
Success Metric: Integrate with 1 major EHR system; 0 data breach incidents

### 4.2 Provider Portal Integration

Problem: Doctors need to check if a procedure is covered before ordering.

Solution: API for providers to query coverage (read-only, provider-authenticated)
Benefit: Reduces pre-auth bottlenecks; improves member experience

Effort: 2 weeks (API wrapper + provider onboarding)
Success Metric: 20% of pre-auths submitted via API vs. phone

## Timeline & Resource Estimate

- Phase 1 (Q4 2026 — Q1 2027): 2 engineers, $50k infrastructure cost → live multi-modal + voice MVP
- Phase 2 (Q1 2027 — Q2 2027): 2 engineers + legal/security, $100k → production-ready, HIPAA certified
- Phase 3 (Q2 2027 — Q3 2027): 3 engineers, $80k → personalized, predictive features
- Phase 4 (Q3 2027 — Q4 2027): 4 engineers + integration PM, $150k → ecosystem open

Total: 11-12 engineer-months over 12 months; $400k infrastructure + legal + ops

## North Star Metrics

1. Member Satisfaction: NPS >50 (vs. industry average ~40)
2. Accuracy: 95%+ on coverage Q correctness (vs. current 94%)
3. Latency: p95 <300ms (vs. current 520ms)
4. Uptime: 99.9% (vs. current manual Minikube)
5. Cost/Query: <$0.05 (including LLM, storage, infrastructure)
6. Time to Resolution: Avg 2 turns to answer (vs. current 3 turns)

## Conclusion

This v2 roadmap moves from POC with synthetic data to production system with real healthcare impact. Multi-modal + voice address friction points. Cloud K8s + compliance eliminate deployment/legal risks. Ecosystem integration creates network effects.

The current v1 proved the core thesis: RAG + retrieval works for healthcare Q&A. V2 scales it to production and builds the moat.
