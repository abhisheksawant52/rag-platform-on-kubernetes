# ☸️ RAG Platform on Kubernetes

![Kubernetes](https://img.shields.io/badge/Kubernetes-Production-blue)
![ArgoCD](https://img.shields.io/badge/ArgoCD-GitOps-red)
![Helm](https://img.shields.io/badge/Helm-Deployed-green)

## Overview
Enterprise Kubernetes deployment platform for Retrieval-Augmented Generation workloads.

## Features
- Kubernetes deployment
- Helm packaging
- ArgoCD GitOps
- Prometheus monitoring
- Grafana dashboards
- Multi-environment overlays
- CI/CD automation

## Architecture

User -> Ingress -> FastAPI
                   -> RAG Service
                   -> Vector Database

ArgoCD -> Kubernetes Cluster
Prometheus -> Grafana
