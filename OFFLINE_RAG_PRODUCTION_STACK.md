# Offline On-Premises RAG Production Stack

## Primary Requirements

This architecture is designed for a commercial production workload with the following hard requirements:

1. Run 100% on-premises in a totally air-gapped, closed environment with no internet dependency.
2. Avoid license fees, metered API usage, SaaS subscriptions, or hidden deployment costs for production use.
3. Support local development on an RTX 4080 workstation.
4. Scale to approximately 100GB of private document data.
5. Support both simple one-shot RAG and agentic RAG workflows.

## Recommended Stack

| Layer | Component | License / Cost Position | Production Role |
|---|---|---|---|
| Orchestration | LangGraph Python runtime | MIT for core library | State machine for one-shot RAG, agent loops, routing, retries, and circuit breakers. |
| Inference Engine | vLLM | Apache 2.0 | Local high-throughput LLM serving with OpenAI-compatible API support. |
| Reasoning LLM | Llama 3.1 70B or equivalent open-weight model | Model-specific license; no per-token fee when self-hosted | Main answer synthesis, tool calling, and agent reasoning. |
| Development LLM | Smaller local model, such as Llama 3.1 8B, Qwen, Mistral, or quantized 14B/32B model | Model-specific license | RTX 4080-friendly local development and testing. |
| Vector Database | Qdrant Docker/self-hosted | Apache 2.0 | Stores dense vectors, payload metadata, and parent-child retrieval mappings. |
| Embedding Server | Hugging Face Text Embeddings Inference | Apache 2.0 | Local embedding and reranker model hosting. |
| Embedding Model | BGE-M3 | MIT | Multilingual dense embeddings for large-scale document retrieval. |
| Reranker | BGE-Reranker-Large or BGE-Reranker-v2-M3 | MIT | Reorders retrieved chunks before final answer generation. |
| Data Parsing | Unstructured local package/container | Apache 2.0 core | Extracts text and tables from PDFs, DOCX, HTML, TXT, and other offline files. |
| Observability | Langfuse self-hosted core | MIT/open-core | Local tracing for prompts, retrieval calls, model latency, and agent behavior. |
| Evaluation | Ragas / DeepEval | Apache 2.0 | Regression testing for retrieval quality, faithfulness, answer relevance, and hallucination risk. |
| Runtime Packaging | Dockerfiles per component | Apache 2.0 | Repeatable local and on-prem deployment without Compose coupling. |

## Licensing Position

The stack should be described as:

> Fully self-hosted, air-gapped RAG architecture using permissive open-source infrastructure components and locally hosted open-weight models, with no SaaS dependency or per-token inference cost.

Avoid describing all models as "open source" or "permissive" without checking their exact model license. For example, Llama 3.1 is commercially usable under Meta's Llama Community License, but it is not OSI open source. The infrastructure components listed above are suitable for zero-license-fee self-hosted deployment when using their open-source/core editions.

For strict commercial production, maintain a `THIRD_PARTY_NOTICES.md` file with:

- Component name
- Version
- License
- Source URL
- Model license terms
- Any attribution or redistribution requirement

## Architecture

```text
[ INGESTION PIPELINE ]

Raw Files (.pdf, .docx, .txt, .html)
        |
        v
[ Unstructured Local Parser ]
        |
        v
Clean Document Elements
        |
        v
[ Chunking + Parent Mapping ]
        |
        +--> Parent Documents / Sections / Pages
        |
        v
[ TEI Embedding Server ]
        |
        v
[ Qdrant Vector DB ]

------------------------------------------------------------

[ RUNTIME RAG LOOP ]

User Query
        |
        v
[ LangGraph Workflow ]
        |
        +--> Optional query rewrite / routing
        |
        +--> Qdrant search: retrieve top 25-50 child chunks
        |
        +--> Parent-child expansion: fetch larger parent context
        |
        +--> TEI reranker: compress to top 5-10 passages
        |
        +--> vLLM local model: synthesize grounded final answer
        |
        v
Final Response with Citations
```

## One-Shot RAG Mode

Use one-shot RAG when the user asks a direct question that can be answered from retrieved context.

Typical flow:

1. Embed the user query.
2. Retrieve candidate chunks from Qdrant.
3. Expand child chunks to parent sections.
4. Rerank candidates.
5. Send the best context to the local LLM.
6. Return an answer with citations.

This mode is simpler, faster, easier to evaluate, and should be the default production path.

## Agentic RAG Mode

Use agentic RAG only when the task needs multi-step behavior, such as:

- Searching multiple times with refined queries
- Comparing documents
- Extracting structured facts
- Producing a report
- Calling tools such as metadata filters, table lookup, or document summarization

Agentic RAG must include strict controls:

- LangGraph recursion limit, for example `{"recursion_limit": 10}`
- Maximum tool calls per request
- Maximum retrieved tokens per step
- Timeout per request
- Duplicate-query detection
- Graceful fallback response when the agent cannot complete

## 100GB Data Scale Design

For 100GB of source data, do not rely on a naive vector-only design.

Required design choices:

1. **Parent-child retrieval**
   Store small child chunks for accurate vector matching, but return larger parent sections to the LLM.

2. **Stable IDs**
   Use deterministic IDs based on source path, document hash, parser version, chunk index, and parent ID.

3. **Incremental indexing**
   Re-index only changed files. Track file hash, parser version, chunking version, embedding model version, and ingestion timestamp.

4. **On-disk vector storage**
   Configure Qdrant for on-disk vectors and on-disk HNSW where appropriate.

5. **Scalar quantization**
   Use Int8 scalar quantization to reduce memory pressure.

6. **Snapshot backups**
   Schedule Qdrant collection snapshots or full storage snapshots and copy them to a separate local/NAS disk.

7. **Hybrid retrieval**
   Add sparse/BM25-style retrieval or BGE-M3 sparse retrieval when exact terms, part numbers, policy IDs, or legal clauses matter.

8. **Citations and provenance**
   Store metadata for source file, page number, section heading, parent ID, chunk ID, and content hash.

## Qdrant Configuration Requirements

At 100GB scale, Qdrant must be configured intentionally. The exact settings should be benchmarked on the target server, but the production direction is:

- Use on-disk vectors.
- Use on-disk payload storage where useful.
- Use Int8 scalar quantization.
- Tune HNSW `m`, `ef_construct`, and runtime `ef`.
- Keep enough RAM for active HNSW graph traversal and OS page cache.
- Keep Qdrant storage on fast NVMe SSDs.
- Create snapshots on a separate disk or local network storage.

Example conceptual collection settings:

```json
{
  "vectors": {
    "size": 1024,
    "distance": "Cosine",
    "on_disk": true
  },
  "hnsw_config": {
    "on_disk": true
  },
  "quantization_config": {
    "scalar": {
      "type": "int8",
      "quantile": 0.99,
      "always_ram": false
    }
  }
}
```

## RTX 4080 Development Strategy

An RTX 4080 is excellent for developing the full system, but not for comfortably serving a 70B model in production-quality settings.

Recommended local development setup:

- Run Qdrant locally in Docker.
- Run TEI locally for BGE-M3 embeddings.
- Use a smaller local LLM for day-to-day development.
- Keep the same OpenAI-compatible API interface that production vLLM will expose.
- Test agent behavior, ingestion, retrieval, reranking, citations, and evaluation locally.
- Use sampled datasets first, then scale to larger offline test corpora.

Recommended development model options:

- Llama 3.1 8B Instruct
- Qwen 2.5 / Qwen 3 class instruct models
- Mistral / Mixtral class models, depending on VRAM
- Quantized 14B/32B models if latency is acceptable

Production can use a larger GPU server for Llama 3.1 70B or another stronger model while preserving the same application architecture.

## Production Hardware Guidance

For a 100GB document corpus, production hardware should be sized around:

- Fast NVMe SSD storage for Qdrant.
- Enough RAM for Qdrant index traversal, OS cache, ingestion jobs, and metadata.
- Dedicated GPU capacity for the LLM.
- Optional separate GPU or CPU service for embeddings/reranking.
- Separate storage for Qdrant snapshots.

The exact RAM and storage footprint depends on:

- Number of chunks
- Embedding dimensions
- Quantization settings
- Payload metadata size
- HNSW parameters
- Whether hybrid/sparse indexes are enabled
- Snapshot retention policy

## Component-Wise Production Specs

The system should be sized by component instead of as one generic server. A 100GB RAG system stresses the vector database, ingestion pipeline, storage, and backup design. A 70B-class model stresses GPU VRAM and inference throughput. These should be planned separately.

### Vector Database: Qdrant

| Requirement | Minimum Production | Recommended Production |
|---|---|---|
| Workload Fit | 100GB corpus, limited users, one-shot RAG first | 100GB corpus, hybrid search, reranking, concurrent users |
| CPU | 8 to 16 cores | 16 to 32 cores |
| RAM | 64GB to 128GB | 256GB to 512GB |
| Primary Storage | 4TB NVMe SSD | 8TB enterprise NVMe SSD |
| Backup Storage | 4TB to 8TB separate disk/NAS | 8TB to 16TB separate disk/NAS |
| Vector Storage | On-disk vectors required | On-disk vectors required |
| Indexing | On-disk HNSW recommended | On-disk HNSW strongly recommended |
| Quantization | Int8 scalar quantization required | Int8 scalar quantization required, benchmarked per collection |
| Payload Storage | On-disk payload where appropriate | On-disk payload with indexed metadata fields |
| Availability | Single node with scheduled snapshots | Dedicated node, snapshots, restore drills, optional replication if available |

Notes:

- Qdrant should run on fast NVMe, not HDD.
- RAM sizing depends on chunk count, HNSW settings, payload indexes, and hybrid retrieval.
- For 100GB data, benchmark with realistic chunking before final hardware purchase.

### LLM Inference: vLLM

| Requirement | Minimum Production | Recommended Production |
|---|---|---|
| Workload Fit | Pilot, limited users, one-shot RAG | Production, agentic RAG, higher concurrency |
| CPU | 8 to 16 cores | 16 to 32 cores |
| RAM | 64GB | 128GB to 256GB |
| GPU | 1x 24GB VRAM GPU | 2x to 4x 48GB-80GB VRAM GPUs |
| Example GPUs | RTX 4090, RTX 6000 Ada, L40S, A5000/A6000 | L40S, A100 80GB, H100 80GB, RTX 6000 Ada, A6000 |
| Model Class | 8B to 14B instruct model; quantized 32B if latency allows | 32B to 70B-class model, depending on GPU capacity |
| 70B Support | Not recommended on single 24GB GPU | Multi-GPU tensor parallelism or high-memory datacenter GPU setup |
| Serving Engine | vLLM OpenAI-compatible API | vLLM with tensor parallelism and tuned batching |
| Concurrency | Low | Medium to high, depending on GPU count and context length |

Notes:

- Keep the application model API compatible between development and production.
- Use smaller local models for routing, query rewriting, classification, and metadata extraction.
- Treat 70B-class inference as a separate GPU sizing decision, not as a default requirement for every deployment.

### Embeddings and Reranking: TEI

| Requirement | Minimum Production | Recommended Production |
|---|---|---|
| Workload Fit | Shared service for embeddings and reranking | Dedicated service for ingestion and runtime retrieval |
| CPU | 8 cores | 16 to 32 cores |
| RAM | 32GB to 64GB | 64GB to 128GB |
| GPU | Optional; 16GB to 24GB GPU preferred | Dedicated 16GB to 24GB GPU |
| Models | BGE-M3 embeddings, BGE reranker | BGE-M3 embeddings, BGE-Reranker-Large or BGE-Reranker-v2-M3 |
| Throughput | Suitable for low-rate ingestion and runtime queries | Suitable for larger batch ingestion and concurrent runtime queries |
| Deployment | Can share host with other services in pilot | Prefer separate container/service from LLM generation |

Notes:

- Embedding large corpora can take a long time if embeddings share the same GPU as generation.
- In production, separating embeddings/reranking from LLM generation prevents ingestion jobs from slowing user responses.

### Data Pipeline: Parsing, Chunking, and Indexing

| Requirement | Minimum Production | Recommended Production |
|---|---|---|
| Workload Fit | Batch ingestion with controlled schedule | Parallel ingestion with resumable jobs |
| CPU | 8 to 16 cores | 32 to 64 cores |
| RAM | 64GB | 128GB to 256GB |
| GPU | Not required | Optional if OCR or embedding jobs are colocated |
| Working Storage | 2TB NVMe | 4TB to 8TB NVMe |
| Parser | Unstructured local | Unstructured local with parser version tracking |
| Job Control | Basic batch scripts | Queue-based resumable jobs with retry and checkpointing |
| Incremental Indexing | Required | Required with file hash, chunk hash, and embedding version tracking |
| Metadata Store | SQLite/Postgres acceptable | Postgres recommended for indexing state and document metadata |

Notes:

- Track source file hash, parser version, chunking version, embedding model version, and ingestion timestamp.
- Store parent-child mappings outside the vector alone so retrieval behavior remains inspectable and recoverable.

### Orchestration API: LangGraph Application

| Requirement | Minimum Production | Recommended Production |
|---|---|---|
| Workload Fit | One-shot RAG and limited agentic RAG | One-shot RAG plus controlled agentic workflows |
| CPU | 4 to 8 cores | 8 to 16 cores |
| RAM | 16GB to 32GB | 32GB to 64GB |
| GPU | Not required | Not required |
| Runtime | Python service | Python service behind internal reverse proxy |
| Agent Controls | Recursion limit, timeout, max tool calls | Recursion limit, timeout, max tool calls, duplicate-query detection |
| Deployment | Standalone Dockerfiles and run scripts | Standalone Dockerfiles, service manager, or Kubernetes |

Notes:

- Default to one-shot RAG for reliability.
- Enable agentic RAG only for workflows that need multi-step search or tool use.
- Use `{"recursion_limit": 10}` or a similarly strict limit for agent loops.

### Observability: Langfuse Self-Hosted

| Requirement | Minimum Production | Recommended Production |
|---|---|---|
| Workload Fit | Prompt/retrieval tracing for pilot | Full trace history, latency analysis, evaluation support |
| CPU | 4 to 8 cores | 8 to 16 cores |
| RAM | 16GB to 32GB | 64GB |
| Storage | 500GB to 1TB SSD | 2TB+ SSD, depending on retention |
| Database | Local Postgres | Dedicated Postgres |
| Retention | Short retention window | Retention policy by environment and data sensitivity |
| Network | Internal-only | Internal-only |

Notes:

- In an air-gapped environment, traces may contain sensitive document snippets.
- Apply retention limits and access controls from the start.

### Evaluation: Ragas / DeepEval

| Requirement | Minimum Production | Recommended Production |
|---|---|---|
| Workload Fit | Manual or scheduled regression checks | Automated regression suite before releases |
| CPU | 4 to 8 cores | 8 to 16 cores |
| RAM | 16GB to 32GB | 32GB to 64GB |
| GPU | Can reuse LLM server | Prefer scheduled use of LLM server or smaller judge model |
| Dataset Size | Small golden set | Versioned golden set across document types |
| Frequency | Before major changes | Before every release and indexing strategy change |
| Reports | Local Markdown/JSON reports | Local dashboard or stored historical reports |

Notes:

- Keep an offline golden dataset with expected answers and citations.
- Include "not found in documents" questions to test refusal behavior.

### Base Platform

| Requirement | Minimum Production | Recommended Production |
|---|---|---|
| OS | Ubuntu LTS or enterprise Linux | Ubuntu LTS or enterprise Linux |
| Container Runtime | Docker Engine with standalone component containers | Docker Engine, systemd-managed containers, or Kubernetes |
| Network | Internal LAN only | Private network with no public ingress |
| Artifact Supply | Manually loaded images/models | Internal offline registry and package mirror |
| Security | Host firewall and local accounts | Internal TLS, RBAC, audit logs, secrets management |
| Backup | Qdrant snapshots and config backup | Full restore-tested backup plan for Qdrant, metadata DB, configs, and model registry |

## Practical Production Sizing Tiers

| Tier | Best For | Suggested Hardware |
|---|---|---|
| Developer Workstation | Local development on sampled data | RTX 4080, 64GB to 128GB RAM, 2TB to 4TB NVMe |
| Pilot Server | Small team, one-shot RAG, limited users | 16 cores, 128GB RAM, 24GB GPU, 4TB NVMe |
| Department Production | 100GB corpus, reranking, observability | 32 cores, 256GB RAM, 1x to 2x 48GB GPUs, 8TB NVMe |
| Enterprise Production | 70B-class model, agentic RAG, concurrent users | 64 cores, 512GB RAM, 2x to 4x 80GB GPUs, 8TB+ NVMe |

## Hardware Reality Check

The RTX 4080 is suitable for building and testing the full application flow, including ingestion, Qdrant, retrieval, reranking, LangGraph orchestration, and smaller local LLMs. It should be treated as a development machine, not as the target production server for 70B-class inference.

For production, the 100GB document requirement mainly stresses storage, RAM, indexing strategy, and backup design. The 70B reasoning model requirement mainly stresses GPU VRAM and inference throughput. These are separate capacity problems and should be sized separately.

## Operational Controls

Minimum production controls:

- Air-gapped model and container artifact registry
- Reproducible component Dockerfiles and run/deployment manifests
- Offline package mirror or prebuilt wheel/container bundle
- Version-pinned models and containers
- Qdrant snapshot schedule
- Restore drill documentation
- LangGraph recursion limit
- Request timeout
- Tool-call budget
- Retrieval token budget
- Prompt and answer logging in Langfuse
- Evaluation test suite before every release
- Source citation requirement for answers
- Fallback response when no reliable context is found

## Evaluation Plan

Use Ragas or DeepEval to test:

- Context precision
- Context recall
- Faithfulness
- Answer relevance
- Citation correctness
- Refusal behavior when the answer is not in the documents
- Regression against known question-answer pairs
- Retrieval quality before and after chunking/index changes

Maintain a golden evaluation set with:

- Direct factual questions
- Multi-document comparison questions
- Table-heavy questions
- Ambiguous questions
- Questions where the correct response is "not found in the provided documents"

## Portfolio Positioning

Recommended project title:

> Air-Gapped Enterprise RAG Assistant for 100GB Private Document Search

Recommended summary:

> Built a fully on-premises, air-gapped RAG system using local LLM inference, Qdrant vector search, BGE-M3 embeddings, reranking, parent-child retrieval, observability, and automated evaluation. The system supports both fast one-shot RAG and controlled agentic RAG workflows, with no SaaS dependency or per-token inference cost.

## Resume and Job Search Keywords

Use these keywords in a resume, LinkedIn profile, GitHub README, and freelance offering:

- RAG
- Agentic RAG
- LangGraph
- vLLM
- Qdrant
- Vector Database
- Semantic Search
- Hybrid Search
- BGE-M3
- Reranking
- Self-hosted LLM
- Offline AI
- Air-gapped AI
- Local LLM
- LLMOps
- Langfuse
- Ragas
- DeepEval
- Document AI
- Unstructured.io
- Embedding Pipelines
- Retrieval Evaluation
- Private AI
- Enterprise Search
- Knowledge Assistant
- Docker
- GPU Inference
- Quantization
- Parent-Child Retrieval
- On-Prem AI
