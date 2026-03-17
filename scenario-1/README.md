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

## Getting Started

```bash
# Check current pod status
kubectl get pods -n scenario-1

# Your main debugging tools
kubectl describe pod <pod-name> -n scenario-1
kubectl logs <pod-name> -n scenario-1
kubectl get events -n scenario-1 --sort-by='.lastTimestamp'
kubectl get endpoints -n scenario-1

# After making fixes, re-apply
kubectl apply -f scenario-1/k8s/deployment.yaml

# Final verification — service should return JSON
kubectl port-forward svc/event-processor 7070:80 -n scenario-1 &
curl localhost:7070/
curl localhost:7070/healthz
curl localhost:7070/readyz
```

## Tips

- **Be systematic.** Start with `kubectl get`, then `describe`, then `logs`. Don't guess.
- **Check one thing at a time.** Fix, apply, observe. Don't shotgun multiple changes.
- Refer to the `app/Dockerfile` and `app/server.py` — they're working correctly and contain useful clues.
- There is more than one issue.

## Files

```
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
```

## Resetting the Scenario

If you want to start over:

```bash
make reset
```

Or manually:
```bash
kubectl delete ns scenario-1
kubectl apply -f scenario-1/k8s/namespace.yaml
kubectl apply -f scenario-1/k8s/configmap.yaml
kubectl apply -f scenario-1/k8s/secret.yaml

# Restore the original broken deployment.yaml from git, then:
kubectl apply -f scenario-1/k8s/deployment.yaml
```
