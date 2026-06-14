# RAG Platform on Kubernetes

A production-grade Retrieval-Augmented Generation (RAG) platform deployed on Kubernetes, built with FastAPI, Qdrant, and OpenAI.

[![CI/CD](https://github.com/your-org/rag-platform-on-kubernetes/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/rag-platform-on-kubernetes/actions)

---

## Architecture

```
User ──► Ingress (nginx + TLS) ──► FastAPI (RAG API)
                                        │
                                        ├──► Qdrant (vector store)
                                        └──► OpenAI API (LLM + embeddings)

ArgoCD ──► Kubernetes Cluster (EKS)
Prometheus ──► Grafana
```

## Features

| Capability | Implementation |
|---|---|
| RAG API | FastAPI with `/query` and `/ingest` endpoints |
| Vector search | Qdrant via HTTP |
| LLM generation | OpenAI (configurable model) |
| Container | Multi-stage Docker, non-root, read-only FS |
| Kubernetes | Deployment, Service, Ingress, HPA, PDB, NetworkPolicy |
| GitOps | ArgoCD with auto-sync and self-heal |
| Infrastructure | Terraform (EKS + VPC + ECR) |
| Observability | Prometheus metrics, Grafana dashboard, alert rules |
| CI/CD | GitHub Actions (lint → test → scan → build → deploy) |
| Multi-env | Kustomize overlays for staging and production |
| Helm | Full chart with templated resources |

---

## Quick Start

### Prerequisites
- Docker, kubectl, helm, kustomize, terraform
- AWS CLI configured (for EKS)
- OpenAI API key

### Local development
```bash
cd app/
pip install -r requirements.txt
OPENAI_API_KEY=sk-... VECTOR_STORE_URL=http://localhost:6333 \
  uvicorn api.main:app --reload
```

API docs available at http://localhost:8000/docs (non-production only).

### Run tests
```bash
pip install pytest pytest-asyncio pytest-cov httpx
pytest tests/ -v --cov=app
```

### Deploy to Kubernetes

**Helm (recommended for first install)**
```bash
helm install rag-platform helm/ \
  --namespace rag-production \
  --create-namespace \
  --set image.tag=<TAG> \
  --set secrets.openaiApiKey=$OPENAI_API_KEY
```

**Kustomize**
```bash
kustomize build kubernetes/overlays/production | kubectl apply -f -
```

See [docs/runbooks/deployment.md](docs/runbooks/deployment.md) for the full deployment runbook.

---

## Repository Structure

```
.
├── app/
│   ├── api/
│   │   └── main.py          # FastAPI application
│   ├── Dockerfile            # Multi-stage production image
│   └── requirements.txt
├── kubernetes/
│   ├── base/                 # Base Kustomize resources
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── ingress.yaml
│   │   ├── hpa.yaml
│   │   ├── networkpolicy.yaml
│   │   ├── poddisruptionbudget.yaml
│   │   ├── serviceaccount.yaml
│   │   └── kustomization.yaml
│   └── overlays/
│       ├── staging/
│       └── production/
├── helm/                     # Helm chart
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
├── argocd/
│   └── application.yaml      # ArgoCD Application manifest
├── monitoring/
│   ├── prometheus/
│   │   ├── prometheus.yml
│   │   └── rules/
│   │       └── rag-platform.yml
│   └── grafana/
│       └── dashboard.json
├── terraform/
│   └── main.tf               # EKS + VPC + ECR
├── tests/
│   └── test_platform.py
├── .github/
│   └── workflows/
│       └── ci.yml            # 7-stage CI/CD pipeline
└── docs/
    └── runbooks/
        └── deployment.md
```

---

## Configuration

All configuration is supplied via environment variables (12-factor app). Secrets are never stored in the chart — supply them at deploy time via `--set secrets.openaiApiKey=...` or an External Secrets Operator.

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | Chat completion model |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embeddings model |
| `VECTOR_STORE_URL` | `http://qdrant:6333` | Qdrant base URL |
| `COLLECTION_NAME` | `rag_documents` | Qdrant collection |
| `ENVIRONMENT` | `production` | Disables `/docs` in production |
| `TOP_K` | `5` | Default retrieval count |
| `OTLP_ENDPOINT` | *(optional)* | OpenTelemetry collector |

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Liveness probe |
| `/readyz` | GET | Readiness probe |
| `/metrics` | GET | Prometheus metrics |
| `/query` | POST | Submit a RAG query |
| `/ingest` | POST | Ingest documents |

### Query example
```bash
curl -X POST https://rag.example.com/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is retrieval-augmented generation?", "top_k": 5}'
```

### Ingest example
```bash
curl -X POST https://rag.example.com/ingest \
  -H "Content-Type: application/json" \
  -d '{"documents": ["RAG combines retrieval with generation..."]}'
```
