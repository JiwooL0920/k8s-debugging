APP_IMAGE := inference-api
APP_TAG := 1.0.0
KIND_CLUSTER := playground
NAMESPACE := scenario-3
K8S_DIR := k8s
APP_DIR := app

.PHONY: help build load reset clean deploy status verify

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

build: ## Build the Docker image
	docker build -t $(APP_IMAGE):$(APP_TAG) $(APP_DIR)/

load: build ## Build and load image into Kind
	kind load docker-image $(APP_IMAGE):$(APP_TAG) --name $(KIND_CLUSTER)

deploy: ## Apply the broken k8s manifests
	kubectl apply -f $(K8S_DIR)/namespace.yaml
	kubectl apply -f $(K8S_DIR)/configmap.yaml
	kubectl apply -f $(K8S_DIR)/secret.yaml
	kubectl apply -f $(K8S_DIR)/deployment.yaml

clean: ## Delete the namespace and all resources
	kubectl delete ns $(NAMESPACE) --ignore-not-found --wait=false

reset: clean ## Full reset — delete everything, restore broken deployment, redeploy
	@echo "Waiting for namespace cleanup..."
	@while kubectl get ns $(NAMESPACE) >/dev/null 2>&1; do sleep 1; done
	cp $(K8S_DIR)/.deployment.yaml.broken $(K8S_DIR)/deployment.yaml
	$(MAKE) deploy
	@echo ""
	@echo "Scenario reset. Start debugging:"
	@echo "  kubectl get pods -n $(NAMESPACE)"

status: ## Show current pod/svc/endpoint status
	@echo "=== Pods ==="
	@kubectl get pods -n $(NAMESPACE) -o wide 2>/dev/null || echo "No pods"
	@echo ""
	@echo "=== Service ==="
	@kubectl get svc -n $(NAMESPACE) 2>/dev/null || echo "No services"
	@echo ""
	@echo "=== Endpoints ==="
	@kubectl get endpoints -n $(NAMESPACE) 2>/dev/null || echo "No endpoints"
	@echo ""
	@echo "=== Recent Events ==="
	@kubectl get events -n $(NAMESPACE) --sort-by='.lastTimestamp' 2>/dev/null | tail -10 || echo "No events"

verify: ## Verify the fix — port-forward and curl all endpoints
	@echo "Port-forwarding svc/inference-api to localhost:7070..."
	@kubectl port-forward svc/inference-api 7070:80 -n $(NAMESPACE) &
	@sleep 2
	@echo ""
	@echo "=== GET / ==="
	@curl -s localhost:7070/ | python3 -m json.tool 2>/dev/null || echo "FAIL"
	@echo ""
	@echo "=== GET /health ==="
	@curl -s localhost:7070/health | python3 -m json.tool 2>/dev/null || echo "FAIL"
	@echo ""
	@echo "=== GET /ready ==="
	@curl -s localhost:7070/ready | python3 -m json.tool 2>/dev/null || echo "FAIL"
	@echo ""
	@echo "=== GET /api/v1/models ==="
	@curl -s localhost:7070/api/v1/models | python3 -m json.tool 2>/dev/null || echo "FAIL"
	@echo ""
	@-pkill -f "port-forward svc/inference-api" 2>/dev/null
