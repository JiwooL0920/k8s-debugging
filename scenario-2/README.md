# Scenario 2 — Resource Limits & OOMKilled

## Scenario

The **data-processor** service was deployed to the `scenario-2` namespace but the pods keep crashing. Your job is to figure out why the containers are being killed and get the service healthy and serving traffic.

The service is a Python Flask API that processes incoming data. It was containerized, the image was loaded into your local Kind cluster, and the Kubernetes manifests were applied — but something (or several things) went wrong.

## What's Deployed

| Resource | Description |
|---|---|
| **Namespace** | `scenario-2` |
| **ConfigMap** | `data-processor-config` — app configuration (version, env, startup delay) |
| **Secret** | `data-processor-secrets` — API key and DB password |
| **Deployment** | `data-processor` — 2 replicas of the data processor |
| **Service** | `data-processor` — ClusterIP service fronting the deployment |

## The App

A simple Flask API with these endpoints:

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Service info (version, environment) |
| `/healthz` | GET | Liveness probe |
| `/readyz` | GET | Readiness probe |
| `/api/v1/data` | POST | Accept data for processing (returns 202) |

The Docker image was built from `app/` and loaded into the Kind cluster as `data-processor:1.0.0`.

## Your Task

1. Investigate why the deployment is broken
2. Fix all issues in `k8s/deployment.yaml`
3. Verify the service is healthy and reachable

## Getting Started

```bash
# Check current pod status
kubectl get pods -n scenario-2

# Your main debugging tools
kubectl describe pod <pod-name> -n scenario-2
kubectl logs <pod-name> -n scenario-2
kubectl get events -n scenario-2 --sort-by='.lastTimestamp'
kubectl get endpoints -n scenario-2

# After making fixes, re-apply
kubectl apply -f scenario-2/k8s/deployment.yaml

# Final verification — service should return JSON
kubectl port-forward svc/data-processor 7070:80 -n scenario-2 &
curl localhost:7070/
curl localhost:7070/healthz
curl localhost:7070/readyz
```

## Tips

- **Be systematic.** Start with `kubectl get`, then `describe`, then `logs`. Don't guess.
- **Check one thing at a time.** Fix, apply, observe. Don't shotgun multiple changes.
- Refer to the `app/Dockerfile` and `app/server.py` — they're working correctly and contain useful clues.
- Pay attention to the **reason** pods are crashing, not just the status.
- There is more than one issue.

## Files

```
scenario-2/
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
make reset
```
