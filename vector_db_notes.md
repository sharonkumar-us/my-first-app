# Vector Database Comparison — Chroma vs Pinecone (Day 8)

## Comparison Table

| | **Chroma** | **Pinecone** |
|---|---|---|
| **Hosting** | Local (runs on your machine, `PersistentClient`) | Cloud (managed, serverless) |
| **Free tier limits** | No limits — fully free, open source, no account needed | Free tier caps vectors/storage; no credit card required to start, but scales into paid tiers |
| **Latency** | Very low — no network round-trip, data is on disk locally | Network round-trip per query; latency depends on region and connection |
| **Ease of setup** | `pip install chromadb`, create a client, done — no signup | Requires account creation, API key management, dashboard/index setup |
| **Persistence** | `PersistentClient` writes to local disk (`./chroma_data`) | Always persistent by default (cloud-hosted) |
| **Offline capability** | Works fully offline | Requires internet connection |

## Chosen for this program: Chroma

Chroma is the right fit for this training program specifically because it matches every other tool choice we've made so far — Ollama over paid LLM APIs, sentence-transformers over OpenAI's embedding API — all free, local, and requiring no account. It lets the whole pipeline run and be tested completely offline, which matters for a learning environment where you want fast iteration without worrying about API costs or rate limits. For this project's current scale (16 knowledge base chunks), a local vector store is more than sufficient, and Chroma's persistent client means the collection survives between script runs without needing any cloud infrastructure.

## Enterprise access control: how each would handle per-member/per-plan restrictions

**Chroma:** Access control isn't built in — Chroma itself has no concept of "users" or "permissions." In a real enterprise deployment, per-member or per-plan restrictions would need to be enforced at the **application layer**: the backend (FastAPI) would need to filter query results by metadata (e.g., `plan_type` matching the authenticated member's plan) before returning them, or maintain separate collections per tenant/plan. This puts the security burden entirely on the application code — a mistake there means data leaks across members.

**Pinecone:** Also doesn't have per-user auth for querying vectors directly, but it does support **metadata filtering at the query level** (similar to Chroma), and namespaces — a native way to logically partition an index (e.g., one namespace per plan type or per organization) without needing separate indexes. For a real enterprise deployment, Pinecone's managed infrastructure would also handle things like encryption at rest, network isolation, and compliance certifications (SOC 2, HIPAA-eligible configurations) that would otherwise need to be self-managed with a local Chroma deployment.

**Practical implication for this coverage chatbot:** since we're handling health plan and claims data, a production version would need careful thought about where access control actually lives — likely metadata-filtered queries at minimum, with the backend enforcing that a member's session can only see chunks tagged with their own `plan_type`, regardless of which vector DB is used underneath.
