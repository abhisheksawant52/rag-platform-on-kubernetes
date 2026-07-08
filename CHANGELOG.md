# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-08

### Added

- Production RAG platform for Kubernetes: a FastAPI service covering document
  ingestion, embedding, vector retrieval, and grounded answer generation.
- `rag_platform` Python package (`src/` layout) with pluggable embedder and
  vector-store backends, configuration via `RAGPLATFORM_*` environment
  variables, and `/health`, `/ready`, `/query`, and `/ingest` endpoints.
- Helm chart under `helm/` (deployment, service, ingress, HPA, PDB,
  serviceaccount, networkpolicy, secret, ServiceMonitor) for templated,
  environment-specific installs.
- Kustomize base and overlays under `kubernetes/` for `dev`, `staging`, and
  `production` environments.
- Monitoring assets under `monitoring/`: Prometheus scrape config and alert
  rules, a Grafana dashboard, and a ServiceMonitor.
- Multi-stage, non-root `Dockerfile`, test suite, and documentation
  (`docs/architecture.md`, `docs/deployment.md`).
- Open-source hygiene: MIT `LICENSE`, `CONTRIBUTING`, `SECURITY`,
  `CODE_OF_CONDUCT`, CI workflow, pre-commit hooks, issue/PR templates,
  `CODEOWNERS`, and Dependabot.
