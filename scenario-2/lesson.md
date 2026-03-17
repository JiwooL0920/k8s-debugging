# Resource Limits & OOMKilled — Everything You Need to Know

> What we learned from debugging a Kubernetes deployment that kept getting killed, explained from scratch.

---

## Table of Contents

1. [The Big Picture — What We're Working With](#1-the-big-picture)
2. [Resource Requests vs Limits — The Two Knobs](#2-resource-requests-vs-limits)
3. [OOMKilled — What Happens When You Run Out of Memory](#3-oomkilled)
4. [QoS Classes — How Kubernetes Prioritizes Pods](#4-qos-classes)
5. [Container Command & Args — CMD vs ENTRYPOINT Override](#5-container-command-and-args)
6. [Readiness Probes — Why HTTP Method Matters](#6-readiness-probes)
7. [Our Debugging Walkthrough — The 3 Bugs](#7-debugging-walkthrough)
8. [kubectl Cheat Sheet](#8-cheat-sheet)

---

## 1. The Big Picture

Here's what we had:

- A **Flask app** (`server.py`) running with gunicorn, listening on port **8080**
- A **Dockerfile** that builds the app image as `data-processor:1.0.0`
- A **Kind cluster** (Kubernetes in Docker) — a local single-node cluster called `playground`
- A **Deployment** manifest that creates 2 replicas (pods) of the app
- A **Service** manifest that exposes those pods to network traffic

The deployment was **broken with 3 layered bugs**. Each bug revealed the next one — you couldn't see bug #2 until you fixed bug #1.

This scenario focuses on **resource management** — one of the most common sources of production incidents in Kubernetes.

---

## 2. Resource Requests vs Limits

### What They Are

Every container in Kubernetes can declare two resource values for each resource type (CPU, memory):

```yaml
resources:
  requests:
    cpu: "100m"       # what the container needs to be scheduled
    memory: "128Mi"   # what the container needs to be scheduled
  limits:
    cpu: "500m"       # the maximum the container can use
    memory: "256Mi"   # the maximum the container can use
```

### Requests — "What I Need to Be Scheduled"

**Requests** are what the Kubernetes scheduler looks at when deciding **which node** to place your pod on. The scheduler finds a node that has enough **unrequested** resources to satisfy your pod's requests.

```
Node capacity:       4 CPU, 8Gi memory
Already requested:   2 CPU, 5Gi memory
Available:           2 CPU, 3Gi memory

Your pod requests:   100m CPU, 128Mi memory → Fits! Scheduled here.
Your pod requests:   3 CPU, 4Gi memory     → Doesn't fit. Try another node.
```

If **no node** has enough unrequested resources, your pod stays in `Pending` state with a `FailedScheduling` event.

Requests are a **guarantee** — the kubelet reserves this amount for your container. Other containers on the same node can't use it.

### Limits — "The Maximum I'm Allowed to Use"

**Limits** are hard ceilings enforced by the Linux kernel (via cgroups):

- **Memory limit**: If your container tries to use more memory than its limit, the Linux OOM killer **terminates the process**. This is OOMKilled.
- **CPU limit**: If your container tries to use more CPU than its limit, it gets **throttled** — the kernel pauses the process until the next scheduling period. The container doesn't crash; it just runs slower.

This is the critical difference:

| Resource | Exceeds Limit | Consequence |
|----------|--------------|-------------|
| **Memory** | Allocates beyond limit | **Process killed** (OOMKilled, exit code 137) |
| **CPU** | Tries to use beyond limit | **Throttled** (slowed down, not killed) |

### The Relationship Between Requests and Limits

```
0           requests        limits        node capacity
├──────────────┼───────────────┼──────────────────┤
               │               │
  guaranteed   │   burstable   │   forbidden
  (reserved)   │   (can use    │   (OOM killed /
               │    if free)   │    throttled)
```

- **Below requests**: Guaranteed. Always available to your container.
- **Between requests and limits**: Burstable. Container can use this if the node has spare capacity. For memory, the node can reclaim this under pressure.
- **Above limits**: Forbidden. Memory → OOMKilled. CPU → throttled.

### Constraints

- `requests` must be ≤ `limits`. If requests > limits, the API server rejects the pod spec.
- If you specify limits but not requests, requests default to equal limits.
- If you specify neither, the container has no guaranteed resources and no ceiling (unless a LimitRange or ResourceQuota applies).

### Units

**CPU:**
```
1       = 1 vCPU / core
"500m"  = 0.5 CPU (500 millicores)
"100m"  = 0.1 CPU (100 millicores)
"250m"  = 0.25 CPU
```

**Memory:**
```
"128Mi" = 128 mebibytes (128 × 1024² bytes)
"256Mi" = 256 mebibytes
"1Gi"   = 1 gibibyte (1024 Mi)
"64M"   = 64 megabytes (64 × 1000² bytes)  ← note: M vs Mi
```

`Mi` (mebibytes, base 1024) and `M` (megabytes, base 1000) are different. Always use `Mi` to avoid confusion.

---

## 3. OOMKilled

### What OOMKilled Means

When a container exceeds its memory limit, the Linux kernel's **Out-Of-Memory (OOM) killer** terminates the process. Kubernetes reports this as:

```
Last State:     Terminated
  Reason:       OOMKilled
  Exit Code:    137
```

Exit code 137 = 128 + 9, where 9 is the SIGKILL signal. The kernel sends SIGKILL — the process gets no chance to handle it or clean up.

### Why It Happened in Our Exercise

Our broken deployment had:
```yaml
resources:
  requests:
    cpu: "100m"
    memory: "10Mi"
  limits:
    cpu: "500m"
    memory: "10Mi"
```

10Mi is extremely low. Here's what Python + Flask + Gunicorn actually needs:

| Component | Approximate Memory |
|-----------|-------------------|
| Python interpreter | ~10-15 MB |
| Flask + dependencies | ~15-20 MB |
| Gunicorn master process | ~5 MB |
| Each gunicorn worker | ~20-30 MB |
| **Total (2 workers)** | **~70-100 MB** |

With a 10Mi limit, the container is killed the moment Python starts importing modules.

### The CrashLoopBackOff Cycle

When a container is OOMKilled, Kubernetes restarts it (because the Deployment's restart policy defaults to `Always`). But it keeps getting OOMKilled again, creating a cycle:

```
Container starts → exceeds 10Mi → OOMKilled → restart (wait 10s)
→ starts again → OOMKilled → restart (wait 20s)
→ starts again → OOMKilled → restart (wait 40s)
→ ...backoff increases to 5 minutes max
```

This is `CrashLoopBackOff` — Kubernetes is telling you "this container keeps crashing, I'm backing off my restart attempts."

### How to Detect OOMKilled

```bash
# Quick check — look for OOMKilled in status or high restart count
kubectl get pods -n scenario-2

# Detailed view — check Last State section
kubectl describe pod <pod-name> -n scenario-2
# Look for:
#   Last State:  Terminated
#     Reason:    OOMKilled
#     Exit Code: 137

# Check events for OOM
kubectl get events -n scenario-2 --sort-by='.lastTimestamp'
```

### How to Right-Size Memory

1. **Start with what you know**: Check the language runtime's minimum. Python needs ~30MB baseline.
2. **Profile locally**: Run the container with `docker stats` to see actual usage.
3. **Use metrics in production**: `kubectl top pods` (requires metrics-server) shows current usage.
4. **Set requests to typical usage, limits to peak usage + buffer**:
   ```yaml
   resources:
     requests:
       memory: "128Mi"   # typical usage
     limits:
       memory: "256Mi"   # peak + 50-100% buffer
   ```
5. **Monitor over time**: Tools like Prometheus + Grafana show usage trends. VPA (Vertical Pod Autoscaler) can recommend values.

### Common OOMKilled Causes in Production

| Cause | Symptom | Fix |
|-------|---------|-----|
| Limit set too low | Immediate OOMKilled on startup | Increase limits |
| Memory leak in app | OOMKilled after running for hours/days | Fix the leak, increase limits as stopgap |
| Sudden spike (e.g., large request) | Occasional OOMKilled under load | Increase limits, add request size limits |
| JVM/Python not respecting limits | Container doesn't see cgroup limits | Set `-Xmx` for JVM, or use `--max-old-space-size` for Node |

---

## 4. QoS Classes

### What They Are

Kubernetes assigns every pod a **Quality of Service (QoS) class** based on its resource configuration. This determines what happens when the node runs low on memory — which pods get killed first.

### The Three QoS Classes

#### Guaranteed (highest priority — killed last)

All containers have requests **equal to** limits for both CPU and memory:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "256Mi"
  limits:
    cpu: "500m"        # same as request
    memory: "256Mi"    # same as request
```

These pods are the last to be evicted under memory pressure. Use for critical workloads.

#### Burstable (medium priority)

At least one container has requests **different from** limits, or only one of requests/limits is set:

```yaml
resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"        # different from request
    memory: "256Mi"    # different from request
```

Our fixed deployment falls in this category. These pods can be evicted if the node needs memory for Guaranteed pods.

#### BestEffort (lowest priority — killed first)

No containers have any requests or limits set:

```yaml
# No resources section at all
containers:
  - name: my-app
    image: my-app:1.0
    # no resources field
```

These are evicted **first** when the node is under memory pressure. Never use for production workloads.

### How to Check a Pod's QoS Class

```bash
kubectl get pod <pod-name> -n scenario-2 -o jsonpath='{.status.qosClass}'
# Output: Burstable
```

### Eviction Order Under Memory Pressure

```
Node running low on memory:

1. Kill BestEffort pods first (no guarantees)
2. Kill Burstable pods that exceed their requests (using more than promised)
3. Kill Burstable pods within their requests
4. Kill Guaranteed pods (last resort — node is critically low)
```

### Best Practices

| Workload Type | QoS Class | Why |
|---------------|-----------|-----|
| Production databases | Guaranteed | Predictable, never evicted first |
| API services | Burstable | Can burst for traffic spikes, reasonable priority |
| Batch jobs, dev/test | Burstable or BestEffort | Less critical, can tolerate restarts |

---

## 5. Container Command and Args

### How Kubernetes Overrides Docker CMD/ENTRYPOINT

A Dockerfile defines two things for running a container:

```dockerfile
ENTRYPOINT ["gunicorn"]                          # the executable
CMD ["--bind", "0.0.0.0:8080", "server:app"]    # default arguments
```

Or, more commonly, just CMD:
```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "server:app"]
```

Kubernetes can override both using `command` and `args`:

| Docker | Kubernetes | What It Does |
|--------|------------|-------------|
| `ENTRYPOINT` | `command` | The executable to run |
| `CMD` | `args` | Arguments to the executable |

### The Override Rules

```
                         Kubernetes command     Kubernetes args
                         NOT set                NOT set
Docker ENTRYPOINT   →    ENTRYPOINT runs        with CMD as args
Docker CMD          →    (normal Docker behavior)

                         Kubernetes command     Kubernetes args
                         SET                    NOT set
Docker ENTRYPOINT   →    command replaces       no args
Docker CMD          →    ENTRYPOINT + CMD       (CMD is ignored too)

                         Kubernetes command     Kubernetes args
                         SET                    SET
Docker ENTRYPOINT   →    command replaces       args replaces
Docker CMD          →    ENTRYPOINT             CMD
```

The key rule: **`command` in Kubernetes completely replaces BOTH `ENTRYPOINT` and `CMD` from the Dockerfile.**

### How This Caused Our Bug

Our Dockerfile had:
```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "server:app"]
```

The broken deployment overrode it:
```yaml
command: ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "app:create_app()"]
```

Two problems:
1. **Wrong module**: `app` instead of `server` — the file is `server.py`, not `app.py`
2. **Wrong callable**: `create_app()` instead of `app` — the Flask app object is `app`, not a factory function

Gunicorn tries to `import app` → `ModuleNotFoundError: No module named 'app'` → process exits → `CrashLoopBackOff`.

### The Fix

The cleanest fix is to **remove the `command` field entirely**:

```yaml
containers:
  - name: data-processor
    image: data-processor:1.0.0
    # No command field — uses Dockerfile CMD
```

This is a best practice: let the Dockerfile define how to run the app. Only override `command` when you have a specific reason (like running a different entrypoint for debugging or migration).

### When to Use command Override

| Use Case | Example |
|----------|---------|
| Debugging a container | `command: ["sleep", "infinity"]` |
| Running migrations before app | `command: ["python", "migrate.py"]` |
| Different entrypoint per environment | `command: ["gunicorn", "--workers", "1"]` for dev |
| **Normal operation** | **Don't override** — use Dockerfile CMD |

---

## 6. Readiness Probes

### Quick Recap

Readiness probes tell Kubernetes whether a pod is **ready to receive traffic**. If the probe fails:
- The pod is removed from Service endpoints
- No traffic is routed to it
- The pod keeps running (unlike liveness probe failures, which restart the container)

### HTTP Probes and Methods

When you configure an HTTP readiness probe:

```yaml
readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
```

The kubelet sends an **HTTP GET** request to that path. This is important — **it's always GET**. You cannot configure the kubelet to send POST, PUT, or any other method.

### How This Caused Our Bug

Our readiness probe was:
```yaml
readinessProbe:
  httpGet:
    path: /api/v1/data
    port: 8080
```

But the `/api/v1/data` endpoint only accepts POST:
```python
@app.route("/api/v1/data", methods=["POST"])
def process_data():
    ...
```

When kubelet sends GET to `/api/v1/data`:
- Flask sees a GET request on a POST-only endpoint
- Returns **405 Method Not Allowed**
- Kubelet considers any status outside 200-399 as a failure
- Readiness probe fails → pod removed from endpoints

The pod is perfectly healthy and the app is running — but Kubernetes won't send traffic to it.

### Probe Response Codes

| Status Code | Probe Result |
|-------------|-------------|
| 200-399 | **Success** |
| 400+ | **Failure** |
| Connection refused | **Failure** |
| Timeout | **Failure** |

### Choosing the Right Probe Endpoint

| Probe | Best Practice | Why |
|-------|---------------|-----|
| **Liveness** | `/healthz` — always returns 200 if process is alive | Tells Kubernetes "I'm not deadlocked, don't kill me" |
| **Readiness** | `/readyz` — returns 200 only when ready to serve | Tells Kubernetes "I can handle traffic now" |
| **Startup** | `/healthz` with generous thresholds | Gives slow-starting apps time before liveness kicks in |

Never use a business endpoint (like `/api/v1/data`) as a probe — it may have:
- Method restrictions (POST-only)
- Authentication requirements
- Side effects
- Variable response times

### Debugging Probe Failures

```bash
# See probe failure events
kubectl describe pod <pod-name> -n scenario-2
# Look in Events for:
#   Warning  Unhealthy  Readiness probe failed: HTTP probe failed with statuscode: 405

# Test the endpoint manually from inside the cluster
kubectl exec <pod-name> -n scenario-2 -- curl -s localhost:8080/api/v1/data
# Returns 405 — confirms the probe path is wrong

kubectl exec <pod-name> -n scenario-2 -- curl -s localhost:8080/readyz
# Returns 200 — this is the correct path
```

---

## 7. Our Debugging Walkthrough — The 3 Bugs

### Bug 1: Memory Limit Too Low — OOMKilled

**Symptom:**
```bash
$ kubectl get pods -n scenario-2
NAME                             READY   STATUS             RESTARTS   AGE
data-processor-xxx               0/1     CrashLoopBackOff   4          2m
data-processor-yyy               0/1     OOMKilled          4          2m
```

**How we found it:**
```bash
$ kubectl describe pod data-processor-xxx -n scenario-2
# In Containers section:
  Last State:     Terminated
    Reason:       OOMKilled
    Exit Code:    137
# In resources:
  Limits:
    memory:  10Mi
```

10Mi is absurdly low for Python. The fix: increase to 256Mi.

```yaml
# Before (broken)
resources:
  requests:
    cpu: "100m"
    memory: "10Mi"
  limits:
    cpu: "500m"
    memory: "10Mi"

# After (fixed)
resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"
    memory: "256Mi"
```

---

### Bug 2: Container Command Override — Wrong Module

**Symptom** (only visible after fixing Bug 1):
```bash
$ kubectl get pods -n scenario-2
NAME                             READY   STATUS             RESTARTS   AGE
data-processor-xxx               0/1     CrashLoopBackOff   2          30s
```

Still crashing, but now for a different reason.

**How we found it:**
```bash
$ kubectl logs data-processor-xxx -n scenario-2
...
ModuleNotFoundError: No module named 'app'
```

Check the Dockerfile CMD:
```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "server:app"]
```

Check the deployment's command:
```yaml
command: ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "app:create_app()"]
```

`app:create_app()` vs `server:app` — wrong module reference.

```yaml
# Before (broken)
command: ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "app:create_app()"]

# After (fixed — remove the entire command field)
# Just delete the command line. The Dockerfile CMD is correct.
```

---

### Bug 3: Readiness Probe — Wrong Path

**Symptom** (only visible after fixing Bug 2):
```bash
$ kubectl get pods -n scenario-2
NAME                             READY   STATUS    RESTARTS   AGE
data-processor-xxx               0/1     Running   0          30s
data-processor-yyy               0/1     Running   0          30s

$ kubectl get endpoints data-processor -n scenario-2
NAME             ENDPOINTS   AGE
data-processor   <none>      3m
```

Pods are running but 0/1 Ready. Endpoints are empty.

**How we found it:**
```bash
$ kubectl describe pod data-processor-xxx -n scenario-2
# Events show:
  Warning  Unhealthy  Readiness probe failed: HTTP probe failed with statuscode: 405
```

405 = Method Not Allowed. The readiness probe does GET on `/api/v1/data`, but that endpoint only accepts POST.

```yaml
# Before (broken)
readinessProbe:
  httpGet:
    path: /api/v1/data
    port: 8080

# After (fixed)
readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
```

---

### The Full Debugging Flow (Summary)

```
Step  Command                           What You Learn              Bug Found
─────────────────────────────────────────────────────────────────────────────────
1     kubectl get pods                  Pod status overview         CrashLoopBackOff
2     kubectl describe pod              Last State: OOMKilled       → Bug 1
3     Check resource limits             memory: 10Mi too low        Memory limit
4     (fix → reapply)                                               ─
5     kubectl get pods                  Still CrashLoopBackOff      → Bug 2
6     kubectl logs                      ModuleNotFoundError         Wrong module
7     Compare Dockerfile CMD            server:app is correct       ─
8     (fix → reapply)                                               ─
9     kubectl get pods                  Running but 0/1 Ready       → Bug 3
10    kubectl describe pod              Readiness probe 405         Wrong probe path
11    Check server.py                   /api/v1/data is POST-only   ─
12    (fix → reapply)                                               ─
13    kubectl get pods                  2/2 Ready ✓                 ─
14    make verify                       200 OK                      All fixed ✓
```

---

## 8. kubectl Cheat Sheet

Commands used in this exercise:

| Command | What It Tells You |
|---------|-------------------|
| `kubectl get pods -n <ns>` | Pod status, ready count, restarts |
| `kubectl describe pod <pod> -n <ns>` | Full details — Last State shows OOMKilled |
| `kubectl logs <pod> -n <ns>` | App stdout/stderr — module import errors, etc. |
| `kubectl logs <pod> -n <ns> --previous` | Logs from the previous (crashed) container |
| `kubectl get endpoints <svc> -n <ns>` | Which pod IPs the Service routes to |
| `kubectl top pods -n <ns>` | Current CPU/memory usage (requires metrics-server) |
| `kubectl get pod <pod> -o jsonpath='{.status.qosClass}'` | Pod's QoS class |
| `kubectl get events -n <ns> --sort-by='.lastTimestamp'` | Recent events, newest last |
| `kubectl exec <pod> -n <ns> -- curl -s localhost:8080/readyz` | Test endpoint from inside pod |

### Resource Debugging Decision Tree

```
Pods crashing?
├── Status: OOMKilled / Exit Code 137
│   └── Memory limit too low → increase limits
│       └── Check: kubectl describe pod → Last State: OOMKilled
├── Status: CrashLoopBackOff (not OOM)
│   ├── kubectl logs → import/module errors?
│   │   └── Check command/args override in deployment
│   ├── kubectl logs → app startup errors?
│   │   └── Check env vars, config mounts
│   └── kubectl describe pod → probe failures?
│       └── Check probe path, port, and HTTP method
├── Status: Running but 0/1 Ready
│   └── Readiness probe failing
│       ├── kubectl describe pod → probe status code
│       ├── 405? → Probe hitting POST-only endpoint
│       ├── Connection refused? → Wrong port
│       └── 500? → App error on probe endpoint
└── Status: Pending
    └── Insufficient resources on node
        └── kubectl describe pod → FailedScheduling event
```

---

## Key Takeaways

1. **Memory limits are hard ceilings.** Exceed them and your container is killed instantly (SIGKILL, exit code 137). CPU limits just throttle.
2. **Set memory requests to typical usage, limits to peak + buffer.** Don't guess — measure with `docker stats` or `kubectl top`.
3. **QoS class determines eviction priority.** Guaranteed > Burstable > BestEffort. Production workloads should be at least Burstable.
4. **`command` in Kubernetes replaces the Dockerfile CMD entirely.** Only override it when you have a specific reason. The Dockerfile should define the default way to run your app.
5. **Readiness probes always send GET.** Never point them at POST-only endpoints. Use dedicated health check endpoints (`/readyz`).
6. **OOMKilled vs CrashLoopBackOff vs 0/1 Ready are different problems.** Check `kubectl describe pod` to distinguish between them — the Last State and Events sections tell you exactly what's happening.
7. **`kubectl logs --previous`** shows logs from the crashed container — essential when the current container has already restarted and lost context.
