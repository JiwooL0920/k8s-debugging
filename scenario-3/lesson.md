# Mixed Kubernetes Debugging — Everything You Need to Know

> Five bugs, five root causes, one lesson: real production incidents rarely come in single flavors. This scenario walks through image pull failures, config mismatches, CPU starvation that silently kills pods via probe timeouts, broken probe paths, and a one-character networking mismatch — in one deployment.

---

## Table of Contents

1. [The Big Picture](#1-the-big-picture)
2. [imagePullPolicy — When Kubernetes Fetches Your Image](#2-imagepullpolicy)
3. [ConfigMap Key References — How Env Vars Are Populated](#3-configmap-key-references)
4. [Resource Limits — CPU Starvation and Silent Probe Failures](#4-resource-limits-and-cpu-starvation)
5. [Health Probe Paths — Liveness vs Readiness](#5-health-probe-paths)
6. [Service Selectors — How Traffic Finds Pods](#6-service-selectors)
7. [Our Debugging Walkthrough — The 5 Bugs](#7-debugging-walkthrough)
8. [kubectl Cheat Sheet](#8-cheat-sheet)

---

## 1. The Big Picture

Here's what we had:

- A **Flask app** (`server.py`) running with gunicorn, listening on port **8080**
- A **Dockerfile** that builds `inference-api:1.0.0`
- A **Kind cluster** — a local Kubernetes cluster named `playground`
- A **Deployment** manifest with 2 replicas
- A **ConfigMap** holding database connection info
- A **Service** that should expose the pods to the network

The deployment was broken with **5 layered bugs**. Each bug hid the next — you couldn't see bug #2 until you fixed bug #1. This is intentional: it reflects how real production incidents behave.

---

## 2. imagePullPolicy

### What It Controls

`imagePullPolicy` tells the kubelet (the agent running on each node) whether to fetch the image from a registry before starting a container.

```yaml
containers:
  - name: inference-api
    image: inference-api:1.0.0
    imagePullPolicy: IfNotPresent   # only pull if not already cached
```

### The Three Values

| Policy | Behavior |
|--------|----------|
| `Always` | Pull from registry on every pod start, even if image is cached |
| `IfNotPresent` | Use cached image if available; only pull if missing |
| `Never` | Never pull — fail if image isn't already present on the node |

### The Default Rules

Kubernetes sets `imagePullPolicy` automatically based on the image tag if you don't specify it:

- `image: myapp:latest` → defaults to `Always`
- `image: myapp:1.0.0` → defaults to `IfNotPresent`
- `image: myapp` (no tag) → treated as `latest`, defaults to `Always`

This default behavior exists because `latest` is a moving target. A pinned semantic version is assumed to be immutable, so there's no reason to re-pull it.

### Why It Matters for Local Development

When you load an image into Kind with `kind load docker-image`, the image is pushed directly into the cluster's internal container runtime — it never goes through a registry. If `imagePullPolicy: Always` is set, Kubernetes ignores the local cache and tries to pull from Docker Hub or your configured registry. The pull fails because the image doesn't exist there.

```
Failed to pull image "inference-api:1.0.0": rpc error: ... not found
```

**Rule of thumb for local Kind development**: Always use `imagePullPolicy: IfNotPresent` or `Never`.

### The Tag Mismatch Problem

This scenario had a compounding issue: the image was built as `inference-api:1.0.0` but the Deployment referenced `inference-api:v1.2.3`. Even if the pull policy had been `IfNotPresent`, the image would not have been found in the local cache because the tag didn't match. Both the tag and the policy needed to be corrected.

**Lesson**: The value in `image:` must exactly match what you passed to `kind load docker-image`. Tags are case-sensitive and literal.

---

## 3. ConfigMap Key References

### How ConfigMaps Work

A ConfigMap is a Kubernetes object that stores non-sensitive configuration as key-value pairs:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: inference-api-config
  namespace: scenario-3
data:
  DATABASE_URL: "postgresql://app_user:pass@db:5432/inference"
  CACHE_TTL: "300"
```

### Injecting a Specific Key as an Env Var

You can reference a single key from a ConfigMap to populate one environment variable:

```yaml
env:
  - name: DATABASE_URL
    valueFrom:
      configMapKeyRef:
        name: inference-api-config
        key: DATABASE_URL         # must match a key that exists in the ConfigMap
```

If the key doesn't exist in the ConfigMap, the container never starts:

```
Error: couldn't find key DB_CONNECTION_STRING in ConfigMap scenario-3/inference-api-config
```

The pod stays in `CreateContainerConfigError` — it doesn't crash, it never even tries to start.

### envFrom vs env

Two ways to pull from a ConfigMap:

```yaml
# Inject ALL keys as env vars (bulk)
envFrom:
  - configMapRef:
      name: inference-api-config

# Inject a SPECIFIC key as an env var (precise)
env:
  - name: DATABASE_URL
    valueFrom:
      configMapKeyRef:
        name: inference-api-config
        key: DATABASE_URL
```

`envFrom` is convenient but exposes all keys, including ones your app might not expect. `env` with `configMapKeyRef` is explicit and fails fast if a key is missing — which is what happened here.

### Diagnosing Key Mismatches

```bash
# See what keys the ConfigMap actually has
kubectl get configmap inference-api-config -n scenario-3 -o yaml

# See what keys the Deployment is requesting
kubectl describe pod <pod> -n scenario-3
# Look for: "couldn't find key X in ConfigMap"
```

The fix is always to align the `key:` field in the Deployment with the actual key name in the ConfigMap.

---

## 4. Resource Limits — CPU Starvation and Silent Probe Failures

### Requests vs Limits

Every container can declare two resource values:

```yaml
resources:
  requests:
    cpu: "100m"       # minimum guaranteed by the scheduler
    memory: "128Mi"   # minimum guaranteed by the scheduler
  limits:
    cpu: "500m"       # maximum the container can consume
    memory: "256Mi"   # maximum before the OOM killer activates
```

**Requests** affect scheduling: Kubernetes only places a pod on a node that has enough unallocated resources to satisfy the request. If no node has enough, the pod stays `Pending`.

**Limits** enforce hard caps at runtime:
- CPU limits are enforced via **CPU throttling** — the container slows down but keeps running. The kernel uses CFS (Completely Fair Scheduler) bandwidth control to cap CPU time.
- Memory limits are enforced via the **Linux OOM killer** — when the container exceeds its limit, the kernel kills the process immediately with signal 9 (SIGKILL), exit code 137.

### The Silent Killer: CPU Starvation at Startup

This scenario's resource bug is subtle because it produces **no explicit error pointing to CPU**. Here's what happens with `cpu: "10m"`:

1. Container starts — the kubelet schedules it and the process launches
2. Python interpreter begins loading (heavily throttled at 1% of a CPU core)
3. Gunicorn and Flask load slowly — startup that normally takes 1–2 seconds takes 30–60+ seconds
4. Liveness probe fires at `initialDelaySeconds: 5`, then again at 15s, 25s
5. The app isn't listening yet — kubelet gets `connection refused`
6. After `failureThreshold: 3` failures, the kubelet kills the container
7. Container restarts → repeat → `CrashLoopBackOff`

What you see in `kubectl describe pod`:

```
Events:
  Warning  Unhealthy  Liveness probe failed: Get "http://10.x.x.x:8080/healthz":
           dial tcp 10.x.x.x:8080: connect: connection refused
  Warning  Killing    Container inference-api failed liveness probe, will be restarted
```

**There is no mention of CPU anywhere.** This looks identical to a crashing application. The only way to surface the resource constraint is:

```bash
kubectl top pod -n scenario-3
# NAME                    CPU(cores)   MEMORY(bytes)
# inference-api-abc123    10m          18Mi          ← CPU pinned at limit
```

CPU pinned at 100% of its limit with a very low absolute value is the signal.

### Why 10m Is Too Low

10 millicores = 1/100th of a single CPU core. Python processes are not CPU-light at startup:

| Phase | CPU Activity |
|-------|-------------|
| CPython interpreter init | Module imports, bytecode compilation |
| Gunicorn master process | Fork workers, set up signal handlers |
| Flask app load | Register routes, initialize extensions |
| Startup delay thread | `time.sleep(5)` — barely any CPU, but blocked |

All of this happens serially while the scheduler only grants the container 10ms of CPU time per second. A startup sequence that takes 1s normally can take 60–100s under 10m throttling.

### OOMKilled — The Other Resource Failure Mode

With `memory: "32Mi"` also set too low, OOMKill is a second risk — but in this scenario, the liveness probe kills the container first. If you raised CPU but left memory at 32Mi, you'd then see:

```
Last State:
  Reason:       OOMKilled
  Exit Code:    137
```

Exit code 137 = 128 + 9 (SIGKILL from the OOM killer). This IS explicit — `kubectl describe` shows the reason directly. Memory failures are noisier than CPU failures, which makes CPU starvation harder to catch.

### Choosing Sane Defaults

For a small Python Flask API with 2 gunicorn workers:

```yaml
resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"
    memory: "256Mi"
```

Start conservative. After deploy, run `kubectl top pod` under real load and tune from there. Never set limits lower than the startup footprint of your runtime.

### QoS Classes

The ratio between requests and limits determines the pod's Quality of Service class:

| QoS Class | Rule | Eviction Priority |
|-----------|------|-------------------|
| `Guaranteed` | requests == limits for all resources | Last to be evicted |
| `Burstable` | requests < limits (at least one resource) | Middle |
| `BestEffort` | no requests or limits set | First to be evicted |

In this scenario, `cpu: "10m"` as both request and limit gives a `Guaranteed` QoS class — which sounds good, but the guarantee is for a limit so low the app can't function.

---

## 5. Health Probe Paths

### Why Probes Exist

Kubernetes doesn't know if your app is actually working — it only knows if the container process is running. Probes give it a way to check application health directly.

### Liveness vs Readiness

| Probe | Question | Failure action |
|-------|----------|----------------|
| **Liveness** | Is the container alive? Should it be restarted? | Kill + restart the container |
| **Readiness** | Is the container ready to accept traffic? | Remove from Service endpoints |

A pod can be `Running` (process alive) but `0/N Ready` (readiness probe failing). In that state:
- The pod is NOT added to the Service's endpoint list
- `kubectl get endpoints` shows `<none>`
- Traffic from the Service never reaches the pod

### HTTP GET Probes

```yaml
livenessProbe:
  httpGet:
    path: /health     # must match an actual route in your app
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready      # must match an actual route in your app
    port: 8080
  initialDelaySeconds: 3
  periodSeconds: 5
  failureThreshold: 3
```

The kubelet makes an HTTP GET request to `<pod-ip>:<port><path>`. Any 2xx or 3xx response is a success. 4xx and 5xx are failures.

### The Naming Convention Trap

Kubernetes has no enforcement around what you name your health endpoints. Common conventions:

- `/healthz`, `/health`, `/ping` for liveness
- `/readyz`, `/ready`, `/readiness` for readiness

Neither convention is enforced. The only thing that matters is that the path in your probe matches the route your app actually exposes. In this scenario, the app exposed `/health` and `/ready`, but the probes pointed to `/healthz` and `/readyz`. Flask returned 404 for both — a 404 is a probe failure.

### Diagnosing Failing Probes

```bash
kubectl describe pod <pod> -n scenario-3
```

Look for events like:

```
Warning  Unhealthy  Readiness probe failed: HTTP probe failed with statuscode: 404
Warning  Unhealthy  Liveness probe failed: HTTP probe failed with statuscode: 404
```

Then look at `app/server.py` and find the actual `@app.route` definitions. The routes in the probe config must match exactly.

### Startup Delay and initialDelaySeconds

The app in this scenario has a simulated startup delay (like loading a model or connecting to a database). `initialDelaySeconds` gives the container time to initialize before probes start firing. If probes start too early, they fail before the app is ready and trigger unnecessary restarts.

---

## 6. Service Selectors

### How Services Route Traffic

A Service doesn't connect to pods directly. It uses a **label selector** to discover which pods should receive traffic:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: inference-api
spec:
  selector:
    app: inference-api     # selects pods with this label
  ports:
    - port: 80
      targetPort: 8080
```

The Service controller watches for pods matching the selector and populates an **Endpoints** object with their IPs. When a client sends traffic to the Service's ClusterIP, `kube-proxy` (or eBPF in newer clusters) forwards it to one of those pod IPs.

### The Selector Must Match Exactly

Label selectors are **exact-match, case-sensitive**. There is no fuzzy matching:

```yaml
# Pod label
labels:
  app: inference-api      # with hyphen

# Service selector
selector:
  app: inferenceapi       # missing hyphen — ZERO pods matched
```

The endpoints stay empty. The Service exists. The pods are healthy. But nothing connects them.

This class of bug is particularly frustrating because:
- `kubectl get pods` shows pods as `Running` and `Ready`
- `kubectl get svc` shows the Service as active
- Only `kubectl get endpoints` or `kubectl describe svc` reveals the disconnect

### Diagnosing Selector Mismatches

```bash
# Step 1: check if endpoints are populated
kubectl get endpoints -n scenario-3

# Step 2: see what selector the Service is using
kubectl describe svc inference-api -n scenario-3
# Look for: Selector: app=inferenceapi

# Step 3: see what labels the pods actually have
kubectl get pods -n scenario-3 --show-labels
# Look for: app=inference-api

# Compare: inferenceapi vs inference-api
```

The fix is always to make the Service `selector` match the pod template `labels` exactly.

### Selectors vs matchLabels

Note the difference between the Service selector and the Deployment selector:

```yaml
# Deployment — uses matchLabels
spec:
  selector:
    matchLabels:
      app: inference-api    # used to own pods

# Service — uses flat selector
spec:
  selector:
    app: inference-api      # used to route traffic
```

Both must match the pod template labels, but they're defined differently. Deployment selectors support set-based expressions; Service selectors are always equality-based.

---

## 7. Debugging Walkthrough

Here's how the ideal debug session flows through all 5 bugs:

### Phase 1 — ImagePullBackOff

```bash
kubectl get pods -n scenario-3
# NAME                            READY   STATUS             RESTARTS
# inference-api-7d9b6c-xk2p9     0/1     ImagePullBackOff   0

kubectl describe pod inference-api-7d9b6c-xk2p9 -n scenario-3
# Events:
#   Warning  Failed  Failed to pull image "inference-api:v1.2.3": ... not found
#   Normal   Pulling pulling image "inference-api:v1.2.3"
```

Check deployment.yaml: `image: inference-api:v1.2.3` + `imagePullPolicy: Always`. Fix both.

### Phase 2 — CreateContainerConfigError

```bash
kubectl get pods -n scenario-3
# NAME                            READY   STATUS                       RESTARTS
# inference-api-new-pod           0/1     CreateContainerConfigError   0

kubectl describe pod inference-api-new-pod -n scenario-3
# Events:
#   Warning  Failed  Error: couldn't find key DB_CONNECTION_STRING in ConfigMap scenario-3/inference-api-config

kubectl get configmap inference-api-config -n scenario-3 -o yaml
# data:
#   DATABASE_URL: "postgresql://..."  ← the actual key name
```

Fix the `configMapKeyRef.key` from `DB_CONNECTION_STRING` to `DATABASE_URL`.

### Phase 3 — CrashLoopBackOff (no app logs, no explicit CPU error)

```bash
kubectl get pods -n scenario-3
# NAME                   READY   STATUS             RESTARTS
# inference-api-abc123   0/1     CrashLoopBackOff   4

kubectl describe pod inference-api-abc123 -n scenario-3
# Events:
#   Warning  Unhealthy  Liveness probe failed: dial tcp: connect: connection refused
#   Warning  Killing    Container inference-api failed liveness probe, will be restarted

kubectl logs inference-api-abc123 -n scenario-3
# (empty — app never reached the point of emitting logs)

kubectl top pod -n scenario-3
# NAME                    CPU(cores)   MEMORY(bytes)
# inference-api-abc123    10m          18Mi     ← CPU pegged at limit
```

CPU is 100% utilized at a limit so low the app can't start within the probe window. Fix both CPU and memory to reasonable values (`cpu: 100m`, `memory: 128Mi` requests; `cpu: 500m`, `memory: 256Mi` limits).

### Phase 4 — Readiness Probe Failing

```bash
kubectl get pods -n scenario-3
# NAME                   READY   STATUS    RESTARTS
# inference-api-abc123   0/1     Running   0

kubectl describe pod inference-api-abc123 -n scenario-3
# Events:
#   Warning  Unhealthy  Readiness probe failed: HTTP probe failed with statuscode: 404
```

Check `app/server.py`:

```python
@app.route("/health")    # not /healthz
@app.route("/ready")     # not /readyz
```

Fix probe paths.

### Phase 5 — No Endpoints

```bash
kubectl get pods -n scenario-3
# NAME                   READY   STATUS    RESTARTS
# inference-api-abc123   2/2     Running   0   ← Ready!

kubectl get endpoints -n scenario-3
# NAME            ENDPOINTS   AGE
# inference-api   <none>      5m   ← no traffic

kubectl describe svc inference-api -n scenario-3
# Selector:  app=inferenceapi

kubectl get pods -n scenario-3 --show-labels
# app=inference-api  ← hyphen present
```

Fix Service selector from `inferenceapi` to `inference-api`.

```bash
make verify
# All endpoints return 200 ✓
```

---

## 8. Cheat Sheet

```bash
# Pod status overview
kubectl get pods -n scenario-3

# Why is a pod failing?
kubectl describe pod <pod> -n scenario-3

# What is the app logging?
kubectl logs <pod> -n scenario-3

# Is the Service finding any pods?
kubectl get endpoints -n scenario-3

# What selector does the Service use?
kubectl describe svc inference-api -n scenario-3

# What labels do the pods have?
kubectl get pods -n scenario-3 --show-labels

# What keys does the ConfigMap have?
kubectl get configmap inference-api-config -n scenario-3 -o yaml

# How much memory/CPU is a pod actually using?
kubectl top pod -n scenario-3

# Watch pods in real time
kubectl get pods -n scenario-3 -w

# Re-apply after fixing deployment.yaml
kubectl apply -f k8s/deployment.yaml

# Force rollout after config changes
kubectl rollout restart deployment/inference-api -n scenario-3

# Full reset to broken state
make reset
```
