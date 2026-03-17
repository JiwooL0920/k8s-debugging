# Scenario 1 Reference Files

This file contains the actual files from scenario-1 as reference for generating new scenarios.

## README.md

```markdown
# Scenario 1 — Kubernetes Deployment Debugging

## Scenario

The **event-processor** service was deployed to the `scenario-1` namespace but it's not working. Your job is to get it healthy and serving traffic.

The service is a Python Flask API that processes events. It was containerized, the image was loaded into your local Kind cluster, and the Kubernetes manifests were applied — but something (or several things) went wrong.

## What's Deployed

| Resource | Description |
|---|---|
| **Namespace** | `scenario-1` |
| **ConfigMap** | `event-processor-config` — app configuration (version, env, startup delay) |
| **Secret** | `event-processor-secrets` — API key and DB password |
| **Deployment** | `event-processor` — 3 replicas of the event processor |
| **Service** | `event-processor` — ClusterIP service fronting the deployment |

## The App

A simple Flask API with these endpoints:

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Service info (version, environment) |
| `/healthz` | GET | Liveness probe |
| `/readyz` | GET | Readiness probe |
| `/api/v1/events` | POST | Accept events (returns 202) |

The Docker image was built from `app/` and loaded into the Kind cluster as `event-processor:1.2.0`.

## Your Task

1. Investigate why the deployment is broken
2. Fix all issues in `k8s/deployment.yaml`
3. Verify the service is healthy and reachable

## Setup

First, build and deploy the broken scenario:

\`\`\`bash
make load    # Build image and load into Kind cluster
make deploy  # Apply all K8s manifests
\`\`\`

## Getting Started

\`\`\`bash
# Check current pod status
kubectl get pods -n scenario-1

# Your main debugging tools
kubectl describe pod <pod-name> -n scenario-1
kubectl logs <pod-name> -n scenario-1
kubectl get events -n scenario-1 --sort-by='.lastTimestamp'
kubectl get endpoints -n scenario-1

# After making fixes, re-apply
kubectl apply -f scenario-1/k8s/deployment.yaml

# Check status after each fix
make status

# Final verification — service should return JSON
make verify
# Or manually:
# kubectl port-forward svc/event-processor 7070:80 -n scenario-1 &
# curl localhost:7070/
# curl localhost:7070/healthz
# curl localhost:7070/readyz
\`\`\`

## Tips

- **Be systematic.** Start with `kubectl get`, then `describe`, then `logs`. Don't guess.
- **Check one thing at a time.** Fix, apply, observe. Don't shotgun multiple changes.
- Refer to the `app/Dockerfile` and `app/server.py` — they're working correctly and contain useful clues.
- There is more than one issue.

## Files

\`\`\`
scenario-1/
├── app/
│   ├── Dockerfile           # Working — reference only
│   ├── requirements.txt
│   └── server.py            # Working — reference only
├── k8s/
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   └── deployment.yaml      # ← Fix issues here
├── ANSWER_KEY.md             # Open ONLY after you're done
├── lesson.md                 # Deep-dive on all concepts
└── README.md                 # You are here
\`\`\`

## Resetting the Scenario

If you want to start over:

\`\`\`bash
make reset   # Delete namespace, restore broken deployment, redeploy
\`\`\`

To completely remove the scenario:

\`\`\`bash
make clean   # Delete the namespace and all resources
\`\`\`
```

## ANSWER_KEY.md

```markdown
# ANSWER KEY — Scenario 1 Bugs
# DO NOT READ UNTIL YOU'VE FINISHED DEBUGGING

## Scenario: event-processor deployment is broken

### Bug 1: Wrong image tag + pull policy (Layer 1 — immediate)
- **Symptom**: All pods in `ImagePullBackOff`
- **Root cause**: `image: event-processor:latest` but only `:1.2.0` was loaded into Kind. Also `imagePullPolicy: Always` forces a registry pull, which fails in Kind.
- **Fix**: Change to `image: event-processor:1.2.0` and `imagePullPolicy: IfNotPresent` (or `Never`)
- **How to find it**: `kubectl describe pod <pod>` → Events show pull failure

### Bug 2: Wrong container port (Layer 2 — after image fix)
- **Symptom**: Pods start but enter `CrashLoopBackOff` due to failing liveness probes
- **Root cause**: `containerPort: 3000` and probes target port `3000`, but the app (gunicorn) listens on port `8080`
- **Fix**: Change `containerPort` to `8080`, update both probe `port` fields to `8080`
- **How to find it**: `kubectl logs <pod>` shows gunicorn binding to `0.0.0.0:8080`. Probe failures visible in `kubectl describe pod`.

### Bug 3: Label selector mismatch — Service (Layer 3 — after pods are healthy)
- **Symptom**: `kubectl get endpoints event-processor` shows `<none>`. Port-forwarding the Service gives "no endpoints available".
- **Root cause**: Pod labels say `app: event-processer` (typo, double 's'), Service selector says `app: event-processor` (correct spelling). They don't match.
- **Fix**: Either fix the pod template labels to `event-processor` OR fix the Service selector to `event-processer`. Best practice: fix the typo in the Deployment (selector + template labels) to `event-processor`.
- **How to find it**: `kubectl get pods --show-labels -n scenario-1`, compare with `kubectl describe svc event-processor -n scenario-1 | grep Selector`
- **Note**: Changing `spec.selector.matchLabels` on a Deployment requires delete + recreate (it's immutable).

### Bug 4: Service targetPort mismatch (Layer 3b — even after label fix)
- **Symptom**: Service routes to pods but connection refused
- **Root cause**: `targetPort: 3000` but app listens on `8080`
- **Fix**: Change `targetPort` to `8080`
- **How to find it**: `kubectl port-forward svc/event-processor 7070:80 -n scenario-1` → connection refused to backend

## Debugging Flow (ideal walkthrough)

\`\`\`
1. kubectl get pods -n scenario-1              → sees ImagePullBackOff
2. kubectl describe pod <pod> -n scenario-1    → sees pull error for :latest
3. Checks Dockerfile / image tags              → realizes :1.2.0 was built
4. Fixes image tag + imagePullPolicy           → pods start, then CrashLoopBackOff
5. kubectl logs <pod> -n scenario-1            → sees gunicorn on :8080
6. kubectl describe pod <pod>                  → sees probe failures on :3000
7. Fixes containerPort + probe ports to 8080   → pods Running + Ready
8. kubectl port-forward svc/event-processor... → no traffic / connection refused
9. kubectl get endpoints event-processor       → <none>
10. kubectl get pods --show-labels              → sees "event-processer" typo
11. Compares with Service selector              → fixes labels + targetPort
12. Verifies with curl                          → 200 OK, done!
\`\`\`

## Commands to verify final fix

\`\`\`bash
kubectl port-forward svc/event-processor 7070:80 -n scenario-1 &
curl localhost:7070/
curl localhost:7070/healthz
curl localhost:7070/readyz
\`\`\`
```

## Makefile

```makefile
APP_IMAGE := event-processor
APP_TAG := 1.2.0
KIND_CLUSTER := playground
NAMESPACE := scenario-1
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
	@echo "Port-forwarding svc/event-processor to localhost:7070..."
	@kubectl port-forward svc/event-processor 7070:80 -n $(NAMESPACE) &
	@sleep 2
	@echo ""
	@echo "=== GET / ==="
	@curl -s localhost:7070/ | python3 -m json.tool 2>/dev/null || echo "FAIL"
	@echo ""
	@echo "=== GET /healthz ==="
	@curl -s localhost:7070/healthz | python3 -m json.tool 2>/dev/null || echo "FAIL"
	@echo ""
	@echo "=== GET /readyz ==="
	@curl -s localhost:7070/readyz | python3 -m json.tool 2>/dev/null || echo "FAIL"
	@echo ""
	@-pkill -f "port-forward svc/event-processor" 2>/dev/null
```

## app/Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

# App listens on 8080
EXPOSE 8080

# Run with gunicorn for production-like behavior
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "server:app"]
```

## app/server.py

```python
import os
import time
from flask import Flask, jsonify

import threading

app = Flask(__name__)

# Simulate startup delay (like loading ML model or connecting to DB)
STARTUP_DELAY = int(os.environ.get("STARTUP_DELAY_SECONDS", "5"))
ready = False

def initialize():
    global ready
    time.sleep(STARTUP_DELAY)
    ready = True

# Start init thread at import time so it works under gunicorn
threading.Thread(target=initialize, daemon=True).start()

@app.route("/healthz")
def healthz():
    """Liveness probe - am I alive?"""
    return jsonify({"status": "ok"}), 200

@app.route("/readyz")
def readyz():
    """Readiness probe - am I ready to serve traffic?"""
    if ready:
        return jsonify({"status": "ready"}), 200
    return jsonify({"status": "initializing"}), 503

@app.route("/")
def index():
    return jsonify({
        "service": "event-processor",
        "version": os.environ.get("APP_VERSION", "unknown"),
        "environment": os.environ.get("ENVIRONMENT", "unknown"),
    })

@app.route("/api/v1/events", methods=["POST"])
def process_events():
    return jsonify({"accepted": True, "queue": "events"}), 202

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
```

## app/requirements.txt

```
flask==3.1.0
gunicorn==23.0.0
```

## k8s/namespace.yaml

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: scenario-1
```

## k8s/configmap.yaml

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: event-processor-config
  namespace: scenario-1
data:
  APP_VERSION: "1.2.0"
  ENVIRONMENT: "staging"
  STARTUP_DELAY_SECONDS: "3"
  LOG_LEVEL: "info"
```

## k8s/secret.yaml

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: event-processor-secrets
  namespace: scenario-1
type: Opaque
data:
  API_KEY: c2VjcmV0LWtleS0xMjM0NTY=
  DB_PASSWORD: cGFzc3dvcmQxMjM=
```

## k8s/.deployment.yaml.broken (original broken state)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: event-processor
  namespace: scenario-1
  labels:
    app: event-processor
    team: platform
spec:
  replicas: 3
  selector:
    matchLabels:
      app: event-processer
  template:
    metadata:
      labels:
        app: event-processer
    spec:
      containers:
        - name: event-processor
          image: event-processor:latest
          imagePullPolicy: Always
          ports:
            - containerPort: 3000
              protocol: TCP
          envFrom:
            - configMapRef:
                name: event-processor-config
            - secretRef:
                name: event-processor-secrets
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
          livenessProbe:
            httpGet:
              path: /healthz
              port: 3000
            initialDelaySeconds: 2
            periodSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: 3000
            initialDelaySeconds: 1
            periodSeconds: 3
            failureThreshold: 2
---
apiVersion: v1
kind: Service
metadata:
  name: event-processor
  namespace: scenario-1
spec:
  selector:
    app: event-processor
  ports:
    - port: 80
      targetPort: 3000
      protocol: TCP
  type: ClusterIP
```

## k8s/deployment.yaml (fixed version for reference)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: event-processor
  namespace: scenario-1
  labels:
    app: event-processor
    team: platform
spec:
  replicas: 3
  selector:
    matchLabels:
      app: event-processor
  template:
    metadata:
      labels:
        app: event-processor
    spec:
      containers:
        - name: event-processor
          image: event-processor:1.2.0
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8080
              protocol: TCP
          envFrom:
            - configMapRef:
                name: event-processor-config
            - secretRef:
                name: event-processor-secrets
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 2
            periodSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8080
            initialDelaySeconds: 1
            periodSeconds: 3
            failureThreshold: 2
---
apiVersion: v1
kind: Service
metadata:
  name: event-processor
  namespace: scenario-1
spec:
  selector:
    app: event-processor
  ports:
    - port: 80
      targetPort: 8080
      protocol: TCP
  type: ClusterIP
```
