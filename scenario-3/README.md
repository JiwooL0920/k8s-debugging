# Scenario 3 — Mixed Kubernetes Debugging

## Scenario

The **inference-api** service was deployed to the `scenario-3` namespace but it's completely unreachable. Your job is to diagnose all the issues and get it healthy and serving traffic.

The service is a Python Flask API that runs ML model inference. It was containerized, the image was loaded into your local Kind cluster, and the Kubernetes manifests were applied — but multiple things went wrong at different layers.

## What's Deployed

| Resource | Description |
|---|---|
| **Namespace** | `scenario-3` |
| **ConfigMap** | `inference-api-config` — database URL, cache settings, app version |
| **Secret** | `inference-api-secrets` — API key and DB password |
| **Deployment** | `inference-api` — 2 replicas of the inference API |
| **Service** | `inference-api` — ClusterIP service fronting the deployment |

## The App

A simple Flask API with these endpoints:

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Service info (version, environment) |
| `/health` | GET | Liveness probe |
| `/ready` | GET | Readiness probe |
| `/api/v1/models` | GET | List available ML models |
| `/api/v1/predict` | POST | Run inference (requires `DATABASE_URL` env var) |

The Docker image was built from `app/` and loaded into the Kind cluster as `inference-api:1.0.0`.

## Your Task

1. Investigate why the deployment is broken
2. Fix all issues in `k8s/deployment.yaml`
3. Verify the service is healthy and reachable

## Setup

First, build and deploy the broken scenario:

```bash
make load    # Build image and load into Kind cluster
make deploy  # Apply all K8s manifests
```

## Getting Started

```bash
# Check current pod status
kubectl get pods -n scenario-3

# Your main debugging tools
kubectl describe pod <pod-name> -n scenario-3
kubectl logs <pod-name> -n scenario-3
kubectl get events -n scenario-3 --sort-by='.lastTimestamp'
kubectl get endpoints -n scenario-3

# After making fixes, re-apply
kubectl apply -f scenario-3/k8s/deployment.yaml

# Check status after each fix
make status

# Final verification — service should return JSON
make verify
```

## Tips

- **Be systematic.** Start with `kubectl get`, then `describe`, then `logs`. Don't guess.
- **Fix one thing at a time.** Apply, observe, then move to the next issue.
- Refer to `app/server.py` — it's correct and contains useful clues about endpoint names.
- There are more than two issues. Keep going even after the first fix works.

## Files

```
scenario-3/
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
```

## Resetting the Scenario

If you want to start over:

```bash
make reset   # Delete namespace, restore broken deployment, redeploy
```

To completely remove the scenario:

```bash
make clean   # Delete the namespace and all resources
```
