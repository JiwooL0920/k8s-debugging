# Kubernetes Debugging Exercises

A collection of deliberately broken Kubernetes deployments for learners to diagnose and fix. Each scenario contains layered bugs — fixing one reveals the next, mimicking real production debugging.

## Target Environment

- **Cluster**: Local Kind cluster named `playground`
- **App Stack**: Python 3.11 / Flask 3.1.0 / Gunicorn 23.0.0
- **Container Base**: `python:3.11-slim`

## Getting Started

1. Ensure you have a Kind cluster running:
   ```bash
   kind get clusters  # Should show "playground"
   ```

2. Pick a scenario and navigate to its directory:
   ```bash
   cd scenario-1
   ```

3. Build and deploy:
   ```bash
   make load    # Build image and load into Kind
   make deploy  # Apply K8s manifests
   ```

4. Start debugging:
   ```bash
   kubectl get pods -n scenario-1
   ```

## Scenarios

| # | Topic | Difficulty | Key Concepts |
|---|-------|------------|--------------|
| 1 | Image Pull / Ports / Labels | Beginner | imagePullPolicy, containerPort, label selectors, Service targetPort |
| 2 | Resource Limits & OOMKilled | Beginner | memory limits, OOMKilled, container command override, readiness probes |

## Scenario Structure

Each scenario is self-contained:

```
scenario-N/
├── README.md              # Instructions and hints
├── ANSWER_KEY.md          # Solutions (read after completing)
├── lesson.md              # Deep-dive tutorial on concepts
├── Makefile               # Build, deploy, reset, verify
├── app/                   # Application code (working)
└── k8s/                   # Kubernetes manifests (contains bugs)
```

## Common Commands

| Command | Purpose |
|---------|---------|
| `make build` | Build Docker image |
| `make load` | Build + load image into Kind |
| `make deploy` | Apply K8s manifests |
| `make status` | Show pods, services, endpoints, events |
| `make verify` | Port-forward and test all endpoints |
| `make reset` | Restore broken state and redeploy |
| `make clean` | Delete the namespace |

## Debugging Workflow

```
1. kubectl get pods -n scenario-N           # What's the status?
2. kubectl describe pod <pod> -n scenario-N # Why is it failing?
3. kubectl logs <pod> -n scenario-N         # What does the app say?
4. kubectl get endpoints -n scenario-N      # Is the Service finding pods?
5. kubectl get events -n scenario-N         # Recent cluster events
```

## Contributing

To add a new scenario, use the `/generate-scenario` command in Cursor.
