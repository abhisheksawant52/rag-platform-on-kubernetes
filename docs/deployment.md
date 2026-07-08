# Deployment

This guide covers deploying the RAG Platform to Kubernetes with either Helm or
Kustomize. For a fuller operational runbook (secrets, rollback, troubleshooting)
see [runbooks/deployment.md](runbooks/deployment.md).

## Prerequisites

- Kubernetes >= 1.28, `kubectl`
- `helm` >= 3.14 (for the Helm path)
- `kustomize` >= 5.0 (for the Kustomize path)
- A container image published as `ghcr.io/your-org/rag-platform:<tag>`

## Build and push the image

```bash
make docker-build TAG=<tag>          # builds ghcr.io/your-org/rag-platform:<tag>
docker push ghcr.io/your-org/rag-platform:<tag>
```

## Option A — Helm

The chart lives in [`helm/`](../helm) (`helm/Chart.yaml`, `helm/values.yaml`,
`helm/templates/`).

```bash
# Lint and render first
make helm-lint
make helm-template

# Install
helm install rag-platform helm/ \
  --namespace rag-production \
  --create-namespace \
  --set image.tag=<tag> \
  --set secrets.openaiApiKey=$OPENAI_API_KEY
```

Useful values (`helm/values.yaml`): `replicaCount`, `image.*`, `service.*`,
`ingress.*`, `autoscaling.*`, `pdb.*`, `networkPolicy.enabled`,
`serviceMonitor.enabled`.

Upgrade / rollback:

```bash
helm upgrade rag-platform helm/ --namespace rag-production --atomic --timeout 5m
helm rollback rag-platform <revision> --namespace rag-production
```

## Option B — Kustomize

The base and overlays live in [`kubernetes/`](../kubernetes):

```
kubernetes/
├── base/                      # deployment, service, ingress, hpa,
│                              # networkpolicy, pdb, serviceaccount
└── overlays/
    ├── dev/                   # namespace rag-dev,   1 replica
    ├── staging/               # namespace rag-staging, 1 replica
    └── production/            # namespace rag-production, 3 replicas
```

```bash
# Dev
kubectl apply -k kubernetes/overlays/dev

# Staging / Production
kubectl apply -k kubernetes/overlays/staging
kubectl apply -k kubernetes/overlays/production
```

Set the image per overlay via the `images:` block in each
`kustomization.yaml` (name `ghcr.io/your-org/rag-platform`).

## Secrets

The deployment reads the LLM API key from a secret named
`rag-platform-secrets` (key `openai-api-key`). With Helm, supply it via
`--set secrets.openaiApiKey=...`. With Kustomize, create it out of band:

```bash
kubectl create secret generic rag-platform-secrets \
  --from-literal=openai-api-key=$OPENAI_API_KEY \
  --namespace rag-production
```

## Monitoring

- Prometheus scrape config: `monitoring/prometheus/prometheus.yml`
- Alert rules: `monitoring/prometheus/rules/rag-platform.yml`
- Grafana dashboard: `monitoring/grafana/dashboard.json`
- ServiceMonitor (Prometheus Operator): `monitoring/servicemonitor.yaml`, or
  enable the chart's ServiceMonitor with `--set serviceMonitor.enabled=true`.

## Smoke test

```bash
kubectl port-forward -n rag-production svc/rag-platform 8000:80
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "What is retrieval-augmented generation?"}'
```
