<!-- AUTO-MANAGED: project-description -->
## Project Overview

Kubernetes debugging study repo. Each `scenario-N/` directory contains a deliberately broken K8s deployment for learners to diagnose and fix layer by layer. Bugs are layered — fixing one reveals the next, mimicking real production debugging.

- **Target environment**: Local Kind cluster named `playground`
- **App stack**: Python 3.11 / Flask 3.1.0 / Gunicorn 23.0.0
- **Container base**: `python:3.11-slim`
- **Orchestration**: Kubernetes manifests (Deployment, Service, ConfigMap, Secret, Namespace)

<!-- END AUTO-MANAGED -->

<!-- AUTO-MANAGED: build-commands -->
## Build & Operations

All commands run from the scenario directory (e.g., `scenario-1/`).

| Command | Purpose |
|---|---|
| `make build` | Build Docker image `event-processor:1.2.0` |
| `make load` | Build + load image into Kind cluster |
| `make deploy` | Apply all K8s manifests |
| `make clean` | Delete the namespace |
| `make reset` | Full reset — restore broken state, redeploy |
| `make status` | Show pods, services, endpoints, recent events |
| `make verify` | Port-forward svc to localhost:7070, curl all endpoints |

No test suite or linter — this is an exercise repo, not a production app.

<!-- END AUTO-MANAGED -->

<!-- AUTO-MANAGED: architecture -->
## Architecture

```
k8s-debugging/
└── scenario-N/                     # Self-contained debugging exercise
    ├── README.md                   # Scenario instructions & hints
    ├── ANSWER_KEY.md               # Solutions (read after completing)
    ├── lesson.md                   # Deep-dive tutorial on concepts covered
    ├── Makefile                    # Build, deploy, reset, verify
    ├── app/                        # Application code (working — reference only)
    │   ├── Dockerfile
    │   ├── server.py
    │   └── requirements.txt
    └── k8s/                        # Kubernetes manifests
        ├── namespace.yaml
        ├── configmap.yaml
        ├── secret.yaml
        ├── deployment.yaml         # Contains intentional bugs to fix
        └── .deployment.yaml.broken # Original broken state (used by `make reset`)
```

Each scenario is fully self-contained with its own namespace, Makefile, app, and manifests.

<!-- END AUTO-MANAGED -->

<!-- AUTO-MANAGED: conventions -->
## Conventions

- **Scenario naming**: `scenario-N/` directories at repo root, numbered sequentially
- **K8s namespace**: Matches directory name (e.g., `scenario-1` namespace for `scenario-1/`)
- **Manifest layout**: Deployment + Service combined in `deployment.yaml`; other resources get separate files
- **Reset mechanism**: `.deployment.yaml.broken` stores the original buggy state; `make reset` restores it
- **App code is always correct** — bugs live exclusively in K8s manifests
- **Flask health endpoints**: `/healthz` (liveness), `/readyz` (readiness) with startup delay via background thread
- **Documentation per scenario**: README (instructions), ANSWER_KEY (solutions), lesson.md (concepts tutorial)

<!-- END AUTO-MANAGED -->

<!-- AUTO-MANAGED: patterns -->
## Patterns

- **Layered bugs**: Each scenario chains bugs so fixing bug N reveals bug N+1. Typical layers: image pull → container config → networking/labels → service routing
- **Debugging flow**: `kubectl get pods` → `kubectl describe pod` → `kubectl logs` → `kubectl get endpoints` → `kubectl describe svc`
- **Verification**: Always via `make verify` or manual `kubectl port-forward svc/<name> 7070:80` + `curl`
- **Makefile variables**: `APP_IMAGE`, `APP_TAG`, `KIND_CLUSTER`, `NAMESPACE`, `K8S_DIR`, `APP_DIR` at top of each Makefile

<!-- END AUTO-MANAGED -->
