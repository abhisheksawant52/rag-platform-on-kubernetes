# Deployment Runbook — RAG Platform

## Table of Contents
1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Environment Setup](#environment-setup)
4. [Deploying with Helm](#deploying-with-helm)
5. [Deploying with Kustomize / ArgoCD](#deploying-with-kustomize--argocd)
6. [Secrets Management](#secrets-management)
7. [Rollback Procedures](#rollback-procedures)
8. [Health Checks & Smoke Tests](#health-checks--smoke-tests)
9. [Monitoring & Alerting](#monitoring--alerting)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The RAG Platform exposes a FastAPI service that embeds user queries, retrieves relevant documents from Qdrant (vector store), and generates grounded answers via an LLM (OpenAI).

Key components:
| Component | Technology |
|---|---|
| API | FastAPI (Python 3.12) |
| Vector Store | Qdrant |
| LLM | OpenAI GPT-4o-mini |
| Container Registry | GHCR / ECR |
| CD | ArgoCD (GitOps) |
| Infrastructure | Terraform + EKS |

---

## Prerequisites

```bash
kubectl >= 1.28
helm >= 3.14
kustomize >= 5.0
argocd CLI >= 2.11
terraform >= 1.5
aws-cli >= 2.x (for EKS)
```

---

## Environment Setup

### 1. Provision infrastructure
```bash
cd terraform/
terraform init
terraform workspace select production   # or staging
terraform plan -out=tfplan
terraform apply tfplan
```

### 2. Configure kubectl
```bash
aws eks update-kubeconfig \
  --region us-east-1 \
  --name rag-platform
```

### 3. Create namespaces
```bash
kubectl create namespace rag-production
kubectl create namespace rag-staging
kubectl create namespace monitoring
kubectl create namespace argocd
```

---

## Deploying with Helm

### First install
```bash
helm install rag-platform helm/ \
  --namespace rag-production \
  --create-namespace \
  --set image.tag=<GIT_SHA> \
  --set secrets.openaiApiKey=$OPENAI_API_KEY \
  --values helm/values.yaml
```

### Upgrade
```bash
helm upgrade rag-platform helm/ \
  --namespace rag-production \
  --set image.tag=<GIT_SHA> \
  --set secrets.openaiApiKey=$OPENAI_API_KEY \
  --atomic \       # auto-rollback on failure
  --timeout 5m
```

---

## Deploying with Kustomize / ArgoCD

### Manual Kustomize apply
```bash
# Staging
kustomize build kubernetes/overlays/staging | kubectl apply -f -

# Production
kustomize build kubernetes/overlays/production | kubectl apply -f -
```

### ArgoCD bootstrap
```bash
# Install ArgoCD
kubectl apply -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Register the application
kubectl apply -f argocd/application.yaml

# Trigger immediate sync
argocd app sync rag-platform
```

ArgoCD is configured with `automated.selfHeal=true`, so it will auto-correct drift.

---

## Secrets Management

**Never commit secrets to Git.**

### Option A — kubectl secret (quick)
```bash
kubectl create secret generic rag-platform-secrets \
  --from-literal=openai-api-key=$OPENAI_API_KEY \
  --namespace rag-production
```

### Option B — External Secrets Operator (recommended for production)
Install ESO and configure a `SecretStore` pointing to AWS Secrets Manager or HashiCorp Vault. Then create an `ExternalSecret` CR that syncs `openai-api-key` automatically.

---

## Rollback Procedures

### Helm rollback
```bash
helm history rag-platform -n rag-production
helm rollback rag-platform <REVISION> -n rag-production
```

### Kubernetes rollout undo
```bash
kubectl rollout undo deployment/rag-platform -n rag-production
kubectl rollout status deployment/rag-platform -n rag-production
```

### ArgoCD rollback
```bash
argocd app history rag-platform
argocd app rollback rag-platform <ID>
```

---

## Health Checks & Smoke Tests

```bash
# Liveness
curl -f https://rag.example.com/health

# Readiness
curl -f https://rag.example.com/readyz

# Basic query smoke test
curl -X POST https://rag.example.com/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is RAG?"}' | jq .

# Check pod status
kubectl get pods -n rag-production -l app=rag-platform

# Check HPA
kubectl get hpa rag-platform -n rag-production
```

---

## Monitoring & Alerting

- **Metrics**: Prometheus scrapes `/metrics` on port 8000 (auto-discovered via pod annotations).
- **Dashboard**: Import `monitoring/grafana/dashboard.json` into Grafana.
- **Alerts**: Rules are in `monitoring/prometheus/rules/rag-platform.yml`.

Key SLIs to watch:
| Metric | Target |
|---|---|
| Error rate | < 1% |
| P95 latency | < 5s |
| Pod availability | ≥ 2 replicas |

---

## Troubleshooting

### Pods crash-looping
```bash
kubectl describe pod -l app=rag-platform -n rag-production
kubectl logs -l app=rag-platform -n rag-production --previous
```

### Vector store connection failures
```bash
# Check Qdrant pod
kubectl get pods -l app=qdrant -n rag-production
# Test from within cluster
kubectl run debug --image=curlimages/curl --rm -it -- \
  curl http://qdrant:6333/healthz
```

### High latency
1. Check LLM latency metric: `rag_llm_duration_seconds`
2. Check retrieval latency: `rag_retrieval_duration_seconds`
3. Verify HPA hasn't hit `maxReplicas`
4. Review OpenAI API status at https://status.openai.com

### OOMKilled
Increase `resources.limits.memory` in `helm/values.yaml` and redeploy.
