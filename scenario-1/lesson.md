# Kubernetes Debugging — Everything You Need to Know

> What we learned from debugging a broken Kubernetes deployment, explained from scratch.

---

## Table of Contents

1. [The Big Picture — What We're Working With](#1-the-big-picture)
2. [imagePullPolicy — Why Your Pods Can't Start](#2-imagepullpolicy)
3. [Ports — The Full Chain From Your Terminal to the Container](#3-ports)
4. [Liveness & Readiness Probes — How Kubernetes Checks on Your App](#4-probes)
5. [Services — Stable Networking for Ephemeral Pods](#5-services)
6. [Labels & Selectors — The Glue That Connects Everything](#6-labels-and-selectors)
7. [Endpoints — How Services Find Pods](#7-endpoints)
8. [Testing with port-forward](#8-port-forward)
9. [Our Debugging Walkthrough — The 4 Bugs](#9-debugging-walkthrough)
10. [kubectl Cheat Sheet](#10-cheat-sheet)

---

## 1. The Big Picture

Here's what we had:

- A **Flask app** (`server.py`) running with gunicorn, listening on port **8080**
- A **Dockerfile** that builds the app image as `event-processor:1.2.0`
- A **Kind cluster** (Kubernetes in Docker) — a local single-node cluster called `playground`
- A **Deployment** manifest that creates 3 replicas (pods) of the app
- A **Service** manifest that exposes those pods to network traffic

The deployment was **broken with 4 layered bugs**. Each bug revealed the next one — you couldn't see bug #2 until you fixed bug #1, and so on.

This is exactly how real production debugging works: you fix one thing and the next problem surfaces.

---

## 2. imagePullPolicy

### What It Does

When Kubernetes needs to start a container, it needs the Docker image. `imagePullPolicy` tells Kubernetes **where to get that image from**.

### The Three Options

| Policy | What It Does | When Kubernetes Pulls |
|--------|-------------|----------------------|
| `Always` | Always tries to pull from a remote registry (like Docker Hub, ECR, GCR) | Every time a pod starts |
| `IfNotPresent` | Uses the local image if it exists. Only pulls from a registry if the image isn't already on the node | Only if image is missing locally |
| `Never` | Never pulls from a registry. Only uses images already on the node | Never — fails if image isn't local |

### The Default Behavior (This Is the Tricky Part)

There is **no single default** — it depends on your image tag:

```
image: event-processor:latest     →  default is Always
image: event-processor:1.2.0      →  default is IfNotPresent
image: event-processor             →  same as :latest → default is Always
```

**Why?** Kubernetes assumes that `:latest` is a moving target — the image behind `:latest` could change at any time, so it should always re-pull to get the newest version. But a specific tag like `:1.2.0` is assumed to be immutable — once built, it won't change — so the local copy is fine.

### Why This Mattered in Our Exercise

We were using **Kind** (Kubernetes in Docker). Kind is a local cluster — it has **no connection to Docker Hub or any remote registry**.

We loaded our image directly into Kind with:
```bash
kind load docker-image event-processor:1.2.0 --name playground
```

This places the image directly onto the Kind node's container runtime. It's already there, locally.

**The broken deployment had:**
```yaml
image: event-processor:latest
imagePullPolicy: Always
```

Two problems:
1. `:latest` — we never built a `:latest` tag. We built `:1.2.0`.
2. `Always` — tells Kubernetes to pull from a remote registry. Kind has no registry. So it tries to pull from `docker.io/library/event-processor:latest` and fails.

**The fix:**
```yaml
image: event-processor:1.2.0
imagePullPolicy: IfNotPresent
```

Or, as you discovered: just delete the `imagePullPolicy` line entirely. Since the tag is `:1.2.0` (not `:latest`), the default is `IfNotPresent` — which is exactly what we want.

### When Would You Use Each Policy in the Real World?

| Scenario | Policy | Why |
|----------|--------|-----|
| Local development with Kind/minikube | `IfNotPresent` or `Never` | No registry available |
| Production with immutable tags (`:v2.3.1`) | `IfNotPresent` (default) | Tag won't change, save bandwidth |
| Production with mutable tags (`:latest`, `:staging`) | `Always` | Need to pick up new pushes to same tag |
| Air-gapped / offline environment | `Never` | No network access to registries |
| CI/CD testing with pre-loaded images | `Never` | Guarantee you test the exact image you built |

---

## 3. Ports

Ports were the most confusing part of this exercise, because there are **multiple ports in the chain** and they all need to line up. Let's break down every single one.

### The Full Port Architecture

Here's how a request travels from your terminal all the way to the app:

```
YOUR MACHINE                          KIND CLUSTER
┌─────────────────┐                   ┌──────────────────────────────────────────────────┐
│                 │                   │                                                  │
│  Terminal       │   port-forward    │   Service              Pod                       │
│  ┌───────────┐  │   tunnel          │   ┌──────────────┐    ┌────────────────────────┐ │
│  │ curl      │  │                   │   │              │    │                        │ │
│  │ localhost: │──┼───────────────────┼──▶│  port: 80    │    │  containerPort: 8080   │ │
│  │ 7070      │  │  local:7070       │   │              │──▶ │                        │ │
│  │           │  │  → svc:80         │   │  targetPort: │    │  gunicorn listening    │ │
│  └───────────┘  │                   │   │  8080        │    │  on 0.0.0.0:8080       │ │
│                 │                   │   │              │    │                        │ │
│                 │                   │   └──────────────┘    └────────────────────────┘ │
│                 │                   │                                                  │
└─────────────────┘                   └──────────────────────────────────────────────────┘

The request path:
  curl localhost:7070  →  port-forward tunnel  →  Service :80  →  targetPort :8080  →  gunicorn :8080
```

### Each Port Explained

#### 1. `localhost:7070` — Your Machine

This is the port on **your laptop**. It's completely arbitrary — we picked 7070 because 8080 and 9090 were already in use by other programs on the machine.

You create this with:
```bash
kubectl port-forward svc/event-processor -n scenario-1 7070:80
#                                                           ^^^^
#                                                    local:remote
```

The format is `LOCAL_PORT:REMOTE_PORT`. Local is your machine, remote is the Service.

#### 2. `port: 80` — The Service Port

This is the port that the **Service listens on inside the cluster**. Other pods in the cluster would reach this service at:

```
http://event-processor.scenario-1.svc.cluster.local:80
```

It's the "front door" of the Service. You can pick any port here — 80, 8080, 3000, whatever makes sense for your use case. We used 80 because it's the standard HTTP port.

#### 3. `targetPort: 8080` — Where the Service Forwards To

This is the port **on the pod** that the Service sends traffic to. The Service receives traffic on port 80 and forwards it to port 8080 on the matching pods.

**This MUST match what the application is actually listening on.** In our case, gunicorn binds to `0.0.0.0:8080`, so targetPort must be `8080`.

Our bug: targetPort was `3000` but the app listens on `8080` → connection refused.

#### 4. `containerPort: 8080` — Documentation

Here's the surprising part: **containerPort is mostly informational**. It doesn't actually open or close any ports. Your container will listen on whatever port the application binds to, regardless of what `containerPort` says.

So why declare it?
- **Documentation** — tells other engineers what port the container expects
- **Port naming** — you can give it a name and reference it by name in Services
- **Some tooling** uses it for auto-configuration

But the **probes** DO use the `port` field in their config to know where to send health checks. If you say:

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 3000      ← kubelet sends GET request to pod-ip:3000/healthz
```

And your app is on 8080, the probe hits an empty port → connection refused → probe fails → Kubernetes restarts the container → `CrashLoopBackOff`.

#### 5. `gunicorn --bind 0.0.0.0:8080` — The Actual Application

This is the real source of truth. The Dockerfile says:

```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "server:app"]
```

Gunicorn binds to port 8080 on all interfaces. Everything else in the chain must ultimately point to this port.

### The Golden Rule of Ports

Everything must trace back to what the application actually listens on:

```
Application binds to    → 8080
containerPort should be → 8080
Probe port should be    → 8080
Service targetPort      → 8080
Service port            → anything (we chose 80)
port-forward local      → anything (we chose 7070)
```

---

## 4. Liveness & Readiness Probes

### Why Probes Exist

Kubernetes needs to answer two questions about every container:

1. **Is it alive?** → If no, kill it and restart it.
2. **Is it ready?** → If no, stop sending it traffic (but don't kill it).

These are different questions. A container can be alive but not ready — for example, during startup when it's loading a big ML model or warming up a cache.

### Liveness Probe — "Should I Restart This Container?"

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 2    # wait 2s after container starts before first check
  periodSeconds: 5           # check every 5 seconds
  failureThreshold: 3        # 3 consecutive failures → restart
```

The kubelet (the agent running on each node) sends an HTTP GET to `<pod-ip>:8080/healthz`. If it gets a 200-399 response, the container is alive. If it gets 3 consecutive non-2xx responses (or timeouts), kubelet **kills the container and restarts it**.

**What our app does:**
```python
@app.route("/healthz")
def healthz():
    """Liveness probe - am I alive?"""
    return jsonify({"status": "ok"}), 200   # Always returns 200
```

The liveness endpoint always says "I'm alive" — even during startup. The app process is running, it's just not ready yet.

### Readiness Probe — "Should I Send Traffic Here?"

```yaml
readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  initialDelaySeconds: 1    # wait 1s before first check
  periodSeconds: 3           # check every 3 seconds
  failureThreshold: 2        # 2 consecutive failures → remove from endpoints
```

Same mechanism — kubelet sends HTTP GET to `/readyz`. But instead of restarting the container, a failing readiness probe **removes the pod from the Service's endpoints**. Traffic stops flowing to this pod, but the pod keeps running.

Once the probe passes again, the pod is **added back** to endpoints and starts receiving traffic.

**What our app does:**
```python
ready = False

def initialize():
    global ready
    time.sleep(STARTUP_DELAY)   # Simulate 3-second startup (loading model, connecting to DB)
    ready = True

threading.Thread(target=initialize, daemon=True).start()

@app.route("/readyz")
def readyz():
    if ready:
        return jsonify({"status": "ready"}), 200     # Ready → 200
    return jsonify({"status": "initializing"}), 503   # Not ready → 503
```

During the first 3 seconds: liveness passes (200), readiness fails (503). The pod is alive but not receiving traffic. After initialization completes: both pass.

### What Happens When Probes Fail

| Probe | Fails | Kubernetes Action | Pod Status |
|-------|-------|-------------------|------------|
| Liveness | 3 times in a row | **Kills and restarts** the container | `CrashLoopBackOff` (if keeps failing) |
| Readiness | 2 times in a row | **Removes from endpoints** (no traffic) | `Running` but `0/1 Ready` |
| Both pass | — | Normal operation | `Running` `1/1 Ready` |

### How This Caused Our Bug

The broken deployment had probes pointing to port `3000`:
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 3000          ← Nothing listens on 3000!
```

The kubelet sends GET to `pod-ip:3000/healthz` → connection refused → liveness failure → kubelet kills the container → Kubernetes restarts it → same failure → `CrashLoopBackOff`.

### Bonus: Startup Probe

There's a third probe type: `startupProbe`. It's designed for containers that take a long time to start. While the startup probe is running, liveness and readiness probes are **disabled**. This prevents liveness from killing a slow-starting container.

We didn't use it in this exercise, but in production with heavy apps (e.g., Java apps with 30+ second startup), you'd want one:

```yaml
startupProbe:
  httpGet:
    path: /healthz
    port: 8080
  failureThreshold: 30    # 30 failures × 1s period = 30 seconds to start
  periodSeconds: 1
```

---

## 5. Services

### What Is a Service?

A Service is a **stable network address** for a set of pods.

Here's the problem Services solve: pods are ephemeral. When a pod dies and gets recreated, it gets a **new IP address**. If other services are talking to your pods by IP, they'd break every time a pod restarts.

A Service gives you:
- A **stable ClusterIP** that never changes (e.g., `10.96.214.222`)
- A **DNS name** (e.g., `event-processor.scenario-1.svc.cluster.local`)
- **Load balancing** across all matching pods

### How a Service Connects to Pods

A Service doesn't directly "know about" a Deployment. It finds pods through **label selectors**:

```
Deployment                     Service
┌─────────────────────┐        ┌─────────────────────────┐
│ spec:                │        │ spec:                   │
│   template:          │        │   selector:             │
│     metadata:        │        │     app: event-processor│
│       labels:        │        │                         │
│         app: event-  │◀ ─ ─ ─ │   (finds pods with      │
│         processor    │ match  │    this label)           │
└─────────────────────┘        └─────────────────────────┘
        │                                │
        │ creates                        │ routes to
        ▼                                ▼
┌─────────────────┐            ┌─────────────────┐
│ Pod 1           │            │ Endpoints        │
│ labels:         │            │ 10.244.0.29:8080 │
│   app: event-   │─ ─ ─ ─ ─ ▶│ 10.244.0.30:8080 │
│   processor     │            │ 10.244.0.31:8080 │
│ IP: 10.244.0.29 │            │                  │
├─────────────────┤            └─────────────────┘
│ Pod 2           │
│ IP: 10.244.0.30 │
├─────────────────┤
│ Pod 3           │
│ IP: 10.244.0.31 │
└─────────────────┘
```

The Service continuously watches for pods that match its selector. When pods appear/disappear, the Endpoints list updates automatically.

### Service Types (Brief Overview)

| Type | What It Does | Access From |
|------|-------------|-------------|
| `ClusterIP` (ours) | Internal-only stable IP | Inside the cluster only |
| `NodePort` | Opens a port on every node (30000-32767) | Outside the cluster via `<node-ip>:<node-port>` |
| `LoadBalancer` | Provisions a cloud load balancer (AWS ALB, GCP LB) | Internet / external network |

For this exercise, `ClusterIP` is fine — we access it via port-forward for testing.

### DNS Inside the Cluster

Every Service gets a DNS entry automatically:

```
<service-name>.<namespace>.svc.cluster.local

event-processor.scenario-1.svc.cluster.local
```

From any pod in the cluster, you can reach our service at that address:
```bash
# From inside another pod:
curl http://event-processor.scenario-1.svc.cluster.local:80/healthz
```

---

## 6. Labels and Selectors

### Labels — Key-Value Tags on Resources

Labels are arbitrary key-value pairs attached to Kubernetes resources. They're just metadata — Kubernetes doesn't care what they say. But they're used **everywhere** for selection.

```yaml
metadata:
  labels:
    app: event-processor     # what application is this?
    team: platform           # who owns it?
    environment: staging     # what environment?
```

### Selectors — How Resources Find Each Other

A selector is a query against labels. The Service selector says "find me all pods where `app` equals `event-processor`":

```yaml
# Service
spec:
  selector:
    app: event-processor     # ← I want pods with this label
```

```yaml
# Deployment template (creates pods with these labels)
spec:
  template:
    metadata:
      labels:
        app: event-processor  # ← This must match the Service selector
```

### The Three Label Fields in a Deployment

A Deployment has **three** places where labels/selectors appear, and they must be consistent:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  labels:
    app: event-processor      # ① Deployment's own labels (for organizing Deployments)
spec:
  selector:
    matchLabels:
      app: event-processor    # ② Which pods this Deployment manages (IMMUTABLE!)
  template:
    metadata:
      labels:
        app: event-processor  # ③ Labels applied to pods created by this Deployment
```

- **①** is the Deployment's own label — used to find/organize Deployments, not pods
- **②** tells the Deployment which pods it "owns" — **this is immutable after creation**
- **③** is what actually gets stamped on the pods

**② and ③ MUST match.** If the selector doesn't match the template labels, Kubernetes will reject the manifest.

### The Immutability Problem

`spec.selector.matchLabels` **cannot be changed** with `kubectl apply`. If you need to change it:

```bash
# This will fail:
kubectl apply -f deployment.yaml   # Error: field is immutable

# You must delete and recreate:
kubectl delete deployment event-processor -n scenario-1
kubectl apply -f deployment.yaml
```

This is by design — changing the selector could cause a Deployment to "adopt" or "orphan" pods unexpectedly.

### Our Bug: A Single Character

The broken deployment had a typo:

```yaml
# Deployment
selector:
  matchLabels:
    app: event-processer     # ← typo: double 's'
template:
  metadata:
    labels:
      app: event-processer   # ← same typo (they have to match)

# Service
selector:
  app: event-processor       # ← correct spelling
```

The pods had label `event-processer`. The Service looked for `event-processor`. One character off → zero matches → zero endpoints → no traffic.

How to find this:
```bash
# See what labels the pods actually have
kubectl get pods --show-labels -n scenario-1

# See what the Service is selecting
kubectl describe svc event-processor -n scenario-1 | grep Selector
```

---

## 7. Endpoints

### What Are Endpoints?

Endpoints are the **bridge between a Service and the actual pod IPs**. When a Service's selector matches pods, Kubernetes automatically creates an Endpoints resource that lists every matching pod's IP and port.

```bash
$ kubectl get endpoints event-processor -n scenario-1

NAME              ENDPOINTS                                            AGE
event-processor   10.244.0.29:8080,10.244.0.30:8080,10.244.0.31:8080  2m
```

This means: the Service `event-processor` will load-balance traffic across these three pod IPs on port 8080.

### When Endpoints Show `<none>`

```bash
$ kubectl get endpoints event-processor -n scenario-1

NAME              ENDPOINTS   AGE
event-processor   <none>      2m
```

**This means: no pods match the Service's selector.** The Service exists, it has a ClusterIP, DNS works — but there's nothing behind it. All traffic will fail.

Possible causes:
1. **Label mismatch** (our case — typo in labels)
2. **No pods running** in the namespace
3. **Wrong namespace** — pods and Service are in different namespaces
4. **All pods failing readiness** — if no pods are "ready," they're removed from endpoints

### The Lifecycle

```
1. You create a Service with selector: app=event-processor
2. Kubernetes looks for pods with label app=event-processor
3. Found 3 matching pods → creates Endpoints with their IPs
4. When a pod dies → its IP is removed from Endpoints
5. When a new pod starts and passes readiness → its IP is added
6. If ALL pods fail readiness → Endpoints becomes <none>
```

This is all automatic — you never manually edit Endpoints.

---

## 8. Testing with port-forward

### What port-forward Does

`kubectl port-forward` creates a **tunnel** from your local machine to a resource inside the cluster. It's the easiest way to test Services and pods without setting up Ingress or NodePort.

### Two Ways to Port-Forward

#### 1. Directly to a pod

```bash
kubectl port-forward pod/event-processor-7995786476-kcr7t 7070:8080 -n scenario-1
```

This goes **straight to the pod**, bypassing the Service entirely:
```
localhost:7070 → pod:8080
```

Useful for: testing if the app itself works, regardless of Service config.

#### 2. Through the Service (recommended)

```bash
kubectl port-forward svc/event-processor 7070:80 -n scenario-1
```

This goes **through the Service** — the full chain:
```
localhost:7070 → Service:80 → targetPort:8080 → pod:8080
```

**This is better for debugging** because it tests everything:
- ✅ Service exists and has the right ports
- ✅ Selector matches pods (endpoints populated)
- ✅ targetPort points to the right container port
- ✅ The app responds correctly

If port-forwarding to the pod works but port-forwarding to the Service doesn't, you know the problem is in the Service config (selector, targetPort, etc.).

### The Port Syntax

```bash
kubectl port-forward svc/event-processor 7070:80
#                                         ^^^^
#                                    LOCAL:REMOTE
```

- **LOCAL** (7070) — the port on your laptop. Pick anything that's free.
- **REMOTE** (80) — the port on the Service (its `spec.ports[].port` field).

Then test with curl:
```bash
curl http://localhost:7070/healthz
# {"status":"ok"}

curl http://localhost:7070/readyz
# {"status":"ready"}

curl http://localhost:7070/
# {"service":"event-processor","version":"1.2.0","environment":"staging"}
```

### Why We Used Port 7070

We originally tried:
```bash
kubectl port-forward svc/event-processor 8080:80   # 8080 was in use on our machine
kubectl port-forward svc/event-processor 9090:80   # 9090 was also in use
```

Both ports were occupied by other programs. So we picked 7070 — it was free. The local port is completely arbitrary; it has nothing to do with the cluster.

---

## 9. Our Debugging Walkthrough — The 4 Bugs

Here's the exact sequence we followed to find and fix all 4 bugs. This is the methodology you should use in any Kubernetes debugging scenario.

### Bug 1: Wrong Image Tag + Pull Policy

**Symptom:**
```bash
$ kubectl get pods -n scenario-1
NAME                              READY   STATUS             RESTARTS   AGE
event-processor-74c7fc55c-hwqpw   0/1     ErrImagePull       0          14s
event-processor-74c7fc55c-lw57z   0/1     ImagePullBackOff   0          14s
```

**How we found it:**
```bash
$ kubectl describe pod event-processor-74c7fc55c-hwqpw -n scenario-1
```
In the Events section at the bottom:
```
Failed to pull image "event-processor:latest": ...
```

Kubernetes tried to pull from `docker.io/library/event-processor:latest` — but we're in Kind, there's no registry. And we built `:1.2.0`, not `:latest`.

**The fix:**
```yaml
# Before (broken)
image: event-processor:latest
imagePullPolicy: Always

# After (fixed)
image: event-processor:1.2.0
imagePullPolicy: IfNotPresent    # or just delete this line
```

**Key command:** `kubectl describe pod` — the Events section tells you exactly what went wrong.

---

### Bug 2: Wrong Ports (Container + Probes)

**Symptom** (only visible after fixing Bug 1):
```bash
$ kubectl get pods -n scenario-1
NAME                              READY   STATUS             RESTARTS   AGE
event-processor-xxx               0/1     CrashLoopBackOff   3          2m
```

**How we found it:**
```bash
# Step 1: Check logs — what port is the app on?
$ kubectl logs event-processor-xxx -n scenario-1
[INFO] Listening at: http://0.0.0.0:8080

# Step 2: Check events — why is it crashing?
$ kubectl describe pod event-processor-xxx -n scenario-1
Events:
  Liveness probe failed: connection refused (port 3000)
  Container restarted...
```

The app listens on 8080, but probes are hitting 3000. Liveness fails → container gets killed → restarts → same failure → `CrashLoopBackOff`.

**The fix:**
```yaml
# Before (broken)
ports:
  - containerPort: 3000
livenessProbe:
  httpGet:
    path: /healthz
    port: 3000
readinessProbe:
  httpGet:
    path: /readyz
    port: 3000

# After (fixed)
ports:
  - containerPort: 8080
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
```

**Key commands:** `kubectl logs` (see what the app says) + `kubectl describe pod` (see probe failures).

---

### Bug 3: Label Typo — Service Can't Find Pods

**Symptom** (only visible after fixing Bug 2 — pods are now Running):
```bash
$ kubectl get pods -n scenario-1
NAME                              READY   STATUS    RESTARTS   AGE
event-processor-xxx               1/1     Running   0          1m
event-processor-yyy               1/1     Running   0          1m
event-processor-zzz               1/1     Running   0          1m

# Pods look fine! But...
$ kubectl get endpoints event-processor -n scenario-1
NAME              ENDPOINTS   AGE
event-processor   <none>      3m
```

Endpoints are `<none>` — the Service can't find any pods.

**How we found it:**
```bash
# What labels do the pods have?
$ kubectl get pods --show-labels -n scenario-1
NAME                  READY   STATUS    LABELS
event-processor-xxx   1/1     Running   app=event-processer    ← typo!

# What is the Service looking for?
$ kubectl describe svc event-processor -n scenario-1 | grep Selector
Selector: app=event-processor                                  ← correct spelling
```

`event-processer` ≠ `event-processor`. One letter off, zero endpoints.

**The fix:**
```yaml
# Fix in deployment.yaml
selector:
  matchLabels:
    app: event-processor     # was: event-processer
template:
  metadata:
    labels:
      app: event-processor   # was: event-processer
```

**Important:** Because `spec.selector.matchLabels` is immutable, you can't just `kubectl apply`. You must:
```bash
kubectl delete deployment event-processor -n scenario-1
kubectl apply -f k8s/deployment.yaml
```

**Key commands:** `kubectl get pods --show-labels` + `kubectl get endpoints` + `kubectl describe svc`.

---

### Bug 4: Service targetPort Mismatch

**Symptom** (only visible after fixing Bug 3 — endpoints are now populated):

Endpoints show pod IPs, but curling through the Service gives "connection refused."

**How we found it:**
```bash
$ kubectl describe svc event-processor -n scenario-1
Port:        80/TCP
TargetPort:  3000/TCP    ← wrong! App is on 8080
```

The Service receives traffic on port 80 and forwards to port 3000 on the pods. But nothing listens on 3000.

**The fix:**
```yaml
# Before (broken)
ports:
  - port: 80
    targetPort: 3000

# After (fixed)
ports:
  - port: 80
    targetPort: 8080
```

**Key command:** `kubectl describe svc` — shows you the port mapping.

---

### The Full Debugging Flow (Summary)

```
Step  Command                           What You Learn              Bug Found
─────────────────────────────────────────────────────────────────────────────────
1     kubectl get pods                  Pod status overview         ErrImagePull → Bug 1
2     kubectl describe pod              Pull error details          Wrong image + policy
3     (fix → reapply)                                               ─
4     kubectl get pods                  New status                  CrashLoopBackOff → Bug 2
5     kubectl logs                      App bind port               "Listening at :8080"
6     kubectl describe pod              Probe failure details       Probes hitting :3000
7     (fix → reapply)                                               ─
8     kubectl get pods                  Pods Running ✓              ─
9     kubectl get endpoints             <none>                      → Bug 3
10    kubectl get pods --show-labels    Actual pod labels           "event-processer" typo
11    kubectl describe svc              Service selector            "event-processor" expected
12    (fix → delete + reapply)                                      ─
13    kubectl get endpoints             IPs populated ✓             ─
14    kubectl describe svc              targetPort: 3000            → Bug 4
15    (fix → reapply)                                               ─
16    kubectl port-forward + curl       200 OK                      All fixed ✓
```

---

## 10. kubectl Cheat Sheet

Every command used in this exercise:

| Command | What It Tells You |
|---------|-------------------|
| `kubectl get pods -n <ns>` | Pod names, status (Running/CrashLoop/ErrImagePull), ready count, restarts |
| `kubectl get pods --show-labels -n <ns>` | Same as above + the labels on each pod |
| `kubectl describe pod <pod> -n <ns>` | Full pod details — Events section shows WHY things fail |
| `kubectl logs <pod> -n <ns>` | Application stdout/stderr — see what the app prints |
| `kubectl logs <pod> -n <ns> --previous` | Logs from the PREVIOUS container (before it crashed) |
| `kubectl get svc -n <ns>` | Service names, type, ClusterIP, ports |
| `kubectl describe svc <svc> -n <ns>` | Service details — selector, ports, targetPort |
| `kubectl get endpoints <svc> -n <ns>` | Which pod IPs the Service routes to (`<none>` = no matches) |
| `kubectl get events -n <ns> --sort-by='.lastTimestamp'` | All cluster events, newest last — great overview |
| `kubectl apply -f <file>` | Apply a manifest (create or update) |
| `kubectl delete deployment <name> -n <ns>` | Delete a deployment (needed when changing immutable fields) |
| `kubectl port-forward svc/<svc> LOCAL:REMOTE -n <ns>` | Tunnel from your machine to a Service |
| `kubectl port-forward pod/<pod> LOCAL:REMOTE -n <ns>` | Tunnel directly to a pod (bypasses Service) |

### Debugging Decision Tree

```
Pods not starting?
├── Status: ErrImagePull / ImagePullBackOff
│   └── kubectl describe pod → check image name, tag, pull policy
├── Status: CrashLoopBackOff
│   ├── kubectl logs → app crashing? check error messages
│   └── kubectl describe pod → probe failures? check port config
├── Status: Running but 0/1 Ready
│   └── Readiness probe failing → check /readyz endpoint + port
└── Status: Running 1/1 Ready ✓
    └── Service not working?
        ├── kubectl get endpoints → <none>? Label mismatch
        ├── kubectl describe svc → check targetPort
        └── kubectl port-forward svc/ + curl → test full chain
```

---

## Key Takeaways

1. **Debug layer by layer.** Fix the first error, then the next one appears. Don't try to fix everything at once.
2. **`kubectl describe` is your best friend.** The Events section at the bottom tells you exactly what went wrong.
3. **`kubectl logs` shows you the app's perspective.** What port is it binding to? What errors is it printing?
4. **Endpoints = the connection between Service and pods.** If endpoints are `<none>`, your Service selector doesn't match any pod labels.
5. **Ports must form an unbroken chain:** app binds → containerPort → probe port → targetPort → Service port → port-forward.
6. **imagePullPolicy defaults depend on the tag.** `:latest` → `Always`. Anything else → `IfNotPresent`.
7. **selector.matchLabels is immutable.** If you need to change it, delete and recreate the Deployment.
8. **Test through the Service**, not just the pod. Port-forwarding to the Service proves the entire chain works.
