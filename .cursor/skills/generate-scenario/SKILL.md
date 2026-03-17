---
name: generate-scenario
description: Generate K8s debugging scenarios for the k8s-debugging study repo. Trigger with /generate-scenario or /generate-scenario <topic>. Creates complete scenario directories with layered bugs, documentation, and lesson content. Use when user wants to create a new debugging exercise.
---

# Generate Scenario

Create new Kubernetes debugging scenarios for the k8s-debugging study repo.

**Recommended Model:** This skill involves complex scenario design, multi-file generation, and educational content creation. For best results, use Claude Opus or the most capable model available.

## Trigger

- `/generate-scenario` - Auto-select topic from catalog or web search
- `/generate-scenario <topic>` - Generate scenario for specific topic (e.g., `/generate-scenario pvc`)

## Workflow

### Step 1: Detect Next Scenario Number

```bash
ls -d scenario-*/ 2>/dev/null | wc -l
```

Add 1 to get the next scenario number N.

### Step 2: Check Existing Scenarios

1. Read `README.md` at repo root for scenarios table
2. Verify by scanning `scenario-*/` directories
3. Extract topics from each scenario's README.md if needed

### Step 3: Topic Selection

**If user provides topic:**
1. Match against catalog below
2. Check if topic already exists as a scenario
3. If exists → ask user:
   - "Scenario-X covers this topic. Create variation with different bugs, or search for different topic?"
4. If user wants variation → design different bug patterns
5. If user wants different topic → web search for popular K8s debugging scenarios

**If no topic provided:**
1. Check which catalog topics already have scenarios
2. If unused catalog topics exist → suggest one with difficulty level
3. If all catalog topics used → web search for novel topics from:
   - Kubernetes official troubleshooting docs
   - Production incident case studies
   - DevOps/SRE interview question repositories

### Step 4: Design Bug Layers

Based on topic and difficulty, design bugs that reveal sequentially (fixing bug N reveals bug N+1):

| Difficulty | Bug Count | Example Flow |
|------------|-----------|--------------|
| Beginner | 2-3 | Image pull → Port mismatch → Label typo |
| Intermediate | 3-4 | Init failure → Config missing → Probe wrong → Service selector |
| Advanced | 4-5 | PVC pending → StorageClass missing → Access mode → Mount path → App config |

### Step 5: User Confirmation

Present proposal before creating files:

```
Proposed: scenario-N — [Topic Name]
Difficulty: [Beginner/Intermediate/Advanced]
Bug layers:
  1. [Symptom user will see first]
  2. [Symptom revealed after fixing #1]
  3. [Symptom revealed after fixing #2]
Resources: Deployment, Service, [other resources]

Create this scenario?
```

### Step 6: Generate Files

Create all files following formats in [reference/](reference/) folder.

**Important:** After creating `k8s/deployment.yaml` (with bugs), copy it to `k8s/.deployment.yaml.broken`:
```bash
cp k8s/deployment.yaml k8s/.deployment.yaml.broken
```

This backup is used by `make reset` to restore the broken state.

### Step 7: Update README.md

Add new scenario to the scenarios table in repo root README.md.

## Scenario Catalog

Pre-defined topics with bug patterns ready to use:

| Topic | Difficulty | Bugs | Key Concepts |
|-------|------------|------|--------------|
| Resource Limits (OOMKilled) | Beginner | 2-3 | Memory limits, resource requests, container restarts |
| ConfigMap Mounting | Beginner | 2-3 | Volume mounts, subPath, missing keys |
| Secret Mounting | Beginner | 2-3 | Base64 encoding, mount paths, env injection |
| Init Container Failures | Intermediate | 3-4 | Init containers, dependency ordering, shared volumes |
| Rolling Update Issues | Intermediate | 3-4 | maxUnavailable, maxSurge, readiness gates |
| Service Discovery/DNS | Intermediate | 3-4 | ClusterIP, headless services, DNS resolution |
| PVC/StorageClass | Advanced | 4-5 | PVC binding, StorageClass, access modes, StatefulSet |
| Network Policies | Advanced | 4-5 | Ingress/egress rules, pod selectors, namespace isolation |

## File Structure

Each scenario must have this structure:

```
scenario-N/
├── README.md              # Scenario instructions
├── ANSWER_KEY.md          # Bug solutions + debugging flow
├── lesson.md              # Deep-dive tutorial on concepts
├── Makefile               # Build, deploy, reset, verify commands
├── app/
│   ├── Dockerfile
│   ├── server.py
│   └── requirements.txt
└── k8s/
    ├── namespace.yaml
    ├── configmap.yaml
    ├── secret.yaml
    ├── deployment.yaml    # Contains intentional bugs
    └── .deployment.yaml.broken  # Copy of broken deployment for reset
```

## File Formats

### README.md

```markdown
# Scenario N — [Topic Name]

## Scenario

[2-3 sentences describing what's broken and the user's goal]

## What's Deployed

| Resource | Description |
|---|---|
| **Namespace** | `scenario-N` |
| **ConfigMap** | `[name]` — [description] |
| **Secret** | `[name]` — [description] |
| **Deployment** | `[name]` — [description] |
| **Service** | `[name]` — [description] |

## The App

[Brief description of the app]

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | [description] |
| `/healthz` | GET | Liveness probe |
| `/readyz` | GET | Readiness probe |

## Your Task

1. Investigate why the deployment is broken
2. Fix all issues in `k8s/deployment.yaml`
3. Verify the service is healthy and reachable

## Getting Started

\`\`\`bash
# Check current pod status
kubectl get pods -n scenario-N

# Your main debugging tools
kubectl describe pod <pod-name> -n scenario-N
kubectl logs <pod-name> -n scenario-N
kubectl get events -n scenario-N --sort-by='.lastTimestamp'

# After making fixes, re-apply
kubectl apply -f scenario-N/k8s/deployment.yaml

# Final verification
make verify
\`\`\`

## Tips

- Be systematic. Start with `kubectl get`, then `describe`, then `logs`.
- Fix one thing at a time. Don't shotgun multiple changes.
- There is more than one issue.

## Files

\`\`\`
scenario-N/
├── app/                    # Working — reference only
├── k8s/
│   └── deployment.yaml     # ← Fix issues here
├── ANSWER_KEY.md           # Open ONLY after you're done
└── lesson.md               # Deep-dive on concepts
\`\`\`

## Resetting the Scenario

\`\`\`bash
make reset
\`\`\`
```

### ANSWER_KEY.md

```markdown
# ANSWER KEY — Scenario N Bugs
# DO NOT READ UNTIL YOU'VE FINISHED DEBUGGING

## Scenario: [brief description]

### Bug 1: [Brief Title] (Layer 1 — immediate)
- **Symptom**: [What user sees, e.g., "Pods in CrashLoopBackOff"]
- **Root cause**: [Technical explanation]
- **Fix**: [Exact change needed]
- **How to find it**: [Commands to diagnose]

### Bug 2: [Brief Title] (Layer 2 — after fixing Bug 1)
- **Symptom**: [What user sees after Bug 1 is fixed]
- **Root cause**: [Technical explanation]
- **Fix**: [Exact change needed]
- **How to find it**: [Commands to diagnose]

[Continue for each bug...]

## Debugging Flow (ideal walkthrough)

\`\`\`
1. kubectl get pods -n scenario-N              → sees [symptom]
2. kubectl describe pod <pod> -n scenario-N    → sees [detail]
...
\`\`\`

## Commands to verify final fix

\`\`\`bash
make verify
\`\`\`
```

### lesson.md

```markdown
# [Topic] — Everything You Need to Know

> [One-line summary of what this lesson covers]

---

## Table of Contents

1. [Section 1](#1-section-1)
2. [Section 2](#2-section-2)
...

---

## 1. Section 1

[Explanation with examples]

### Subsection

[Details, code examples, diagrams]

---

## Key Takeaways

1. [Takeaway 1]
2. [Takeaway 2]
...
```

### Makefile

```makefile
APP_IMAGE := [app-name]
APP_TAG := 1.0.0
KIND_CLUSTER := playground
NAMESPACE := scenario-N
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
	@echo "Port-forwarding svc/[service-name] to localhost:7070..."
	@kubectl port-forward svc/[service-name] 7070:80 -n $(NAMESPACE) &
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
	@-pkill -f "port-forward svc/[service-name]" 2>/dev/null
```

### K8s Manifests

**namespace.yaml:**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: scenario-N
```

**configmap.yaml:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: [app-name]-config
  namespace: scenario-N
data:
  KEY: "value"
```

**secret.yaml:**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: [app-name]-secrets
  namespace: scenario-N
type: Opaque
data:
  SECRET_KEY: [base64-encoded-value]
```

**deployment.yaml** (with bugs):
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: [app-name]
  namespace: scenario-N
spec:
  replicas: 3
  selector:
    matchLabels:
      app: [app-name]
  template:
    metadata:
      labels:
        app: [app-name]
    spec:
      containers:
        - name: [app-name]
          image: [image:tag]
          # ... with intentional bugs
---
apiVersion: v1
kind: Service
metadata:
  name: [app-name]
  namespace: scenario-N
spec:
  selector:
    app: [app-name]
  ports:
    - port: 80
      targetPort: 8080
  type: ClusterIP
```

## Key Conventions

- **Namespace** matches directory name (`scenario-N` namespace for `scenario-N/`)
- **App code is always correct** — bugs live exclusively in K8s manifests
- **`.deployment.yaml.broken`** stores original buggy state for `make reset`
- **Flask health endpoints**: `/healthz` (liveness), `/readyz` (readiness)
- **Target cluster**: Kind cluster named `playground`
- **App stack**: Python 3.11 / Flask 3.1.0 / Gunicorn 23.0.0
- **Container base**: `python:3.11-slim`

## Bug Design Patterns

When designing bugs, ensure they reveal sequentially:

| Layer | Bug Type | Symptom | Reveals Next |
|-------|----------|---------|--------------|
| 1 | Image/Pull | ErrImagePull, ImagePullBackOff | Pod starts but... |
| 2 | Container Config | CrashLoopBackOff, probe failures | Pod runs but... |
| 3 | Networking | Endpoints empty, connection refused | Traffic flows but... |
| 4 | App Config | 500 errors, missing env vars | Success |

## Example Bug Patterns by Topic

### Resource Limits (OOMKilled)
1. Memory limit too low (10Mi) → OOMKilled
2. CPU request > limit → Pod rejected
3. Missing resource requests → Unschedulable on resource-constrained node

### ConfigMap Mounting
1. ConfigMap name typo in volume → Pod pending
2. Wrong mount path → App can't find config
3. Missing key in configMapKeyRef → Container crash

### Init Container Failures
1. Init container image wrong → Init:ImagePullBackOff
2. Init container command fails → Init:Error
3. Shared volume not mounted → Main container can't access init output
4. Init timeout too short → Init:CrashLoopBackOff

### PVC/StorageClass
1. PVC references non-existent StorageClass → Pending
2. Access mode mismatch (RWO vs RWX) → Mount fails
3. Volume mount path wrong → App writes to wrong location
4. PVC in wrong namespace → Pod can't find PVC
5. StatefulSet volumeClaimTemplate name mismatch → No PVC created
