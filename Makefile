.DEFAULT_GOAL := help
.PHONY: help install lint format test build clean helm-lint helm-template docker-build

IMAGE ?= ghcr.io/your-org/rag-platform
TAG ?= latest
CHART := helm

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install package with dev dependencies
	python -m pip install --upgrade pip
	pip install -e ".[dev]"

lint: ## Run ruff and black in check mode
	ruff check src tests
	black --check src tests

format: ## Auto-format the codebase
	ruff check --fix src tests
	black src tests

test: ## Run the test suite
	pytest

build: ## Build distribution artifacts
	python -m pip install --upgrade build
	python -m build

clean: ## Remove build and cache artifacts
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

helm-lint: ## Lint the Helm chart
	helm lint $(CHART)

helm-template: ## Render the Helm chart to stdout
	helm template rag-platform $(CHART) --set secrets.openaiApiKey=dummy

docker-build: ## Build the container image
	docker build -t $(IMAGE):$(TAG) .
